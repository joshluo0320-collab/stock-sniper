import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import time
import random

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 名單獲取 (全市場 1,800+ 確保地圖完整)
# ============================================
@st.cache_data(ttl=86400)
def get_verified_list():
    tickers, names_map = [], {}
    backup = {"2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐", "2330": "台積電"}
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=15, headers={'User-Agent': ua})
            res.encoding = 'big5'
            soup = BeautifulSoup(res.text, 'lxml')
            for row in soup.find_all('tr'):
                tds = row.find_all('td')
                if len(tds) > 0:
                    raw = tds[0].text.strip().split()
                    if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                        suffix = ".TW" if "strMode=2" in url else ".TWO"
                        tickers.append(f"{raw[0]}{suffix}")
                        names_map[raw[0]] = raw[1]
        except: continue
    if len(tickers) < 10:
        for k, v in backup.items():
            tickers.append(f"{k}.TW")
            names_map[k] = v
    return tickers, names_map

# ============================================
# 2. 核心分析：油門、壓力、多週期勝率
# ============================================
def execute_master_logic(df, tid, name, vol_gate, trail_p, max_budget):
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    
    last_p = round(float(df['Close'].iloc[-1]), 2)
    if last_p > max_budget: return None

    # [油門分析 - MACD 斜率]
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd_slope = (ema_12 - ema_26).diff().iloc[-1]
    gas_status = "🏎️ 全油門加速" if macd_slope > 0 else "🐢 动力放緩"

    # [路況分析 - 20日壓力牆]
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = df['Close'].iloc[-1] > high_20
    road_status = "🛣️ 前方無壓力" if is_break else "🚧 前方有牆"

    # [能量分析]
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    if avg_v_5 < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5
    energy_status = "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 正常"

    # [勝率計算]
    win_5 = 40 + (30 if df['Close'].iloc[-1] > df['Close'].rolling(5).mean().iloc[-1] else -10)
    win_10 = 40 + (40 if macd_slope > 0 else -15)
    
    # 隔日沖風險
    today_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) * 100
    risk_status = "⚠️ 隔日沖風險" if (v_ratio > 2.5 and today_ret > 7) else "✅ 籌碼穩"

    total_score = int((win_5 * 0.4) + (win_10 * 0.6))
    if is_break: total_score += 10
    
    return {
        "名稱": name, "代號": tid, "綜合勝率": f"{int(min(98, total_score))}%",
        "現價": last_p, "建議進場區": f"{round(last_p * 0.98, 2)}~{round(last_p * 0.995, 2)}",
        "油門分析": gas_status, "路況分析": road_status, "能量": energy_status,
        "5日勝率": f"{min(98, int(win_5))}%", "10日勝率": f"{min(98, int(win_10))}%",
        "風險預警": risk_status, "撤退線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. UI 介面與顯示
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
target_win = st.sidebar.slider("🎯 綜合勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 1.0, 15.0, 7.0, step=0.5)
max_budget = st.sidebar.number_input("💸 單張最高預算 (元)", value=250)

st.title("🏹 2026 全景獵殺系統 v22.2")

if st.button("🔴 啟動全台股地毯獵殺 (1/1800+)", type="primary"):
    final_results = []
    with st.status("📡 獵殺雷達掃描中...", expanded=True) as status:
        tickers, names_map = get_verified_list()
        pb = st.progress(0)
        chunk_size = 40
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            pb.progress(min((i + chunk_size) / len(tickers), 1.0))
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False)
                for t in chunk:
                    tid = t.split(".")[0]
                    df = data[t] if len(chunk) > 1 else data
                    res = execute_master_logic(df, tid, names_map.get(tid, tid), vol_limit, trail_pct, max_budget)
                    if res and int(res['綜合勝率'].replace('%','')) >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺完成！", state="complete")

    if final_results:
        st.success(f"📊 報告：篩選出 {len(final_results)} 支符合標的。")
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        
        # --- 修正排版：手動渲染雙行資訊 ---
        for _, row in df_final.iterrows():
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 2])
                col1.markdown(f"**{row['名稱']}** ({row['代號']})")
                col2.markdown(f"🏆 {row['綜合勝率']}")
                col3.markdown(f"💰 {row['現價']}")
                col4.markdown(f"🎯 {row['建議進場區']}")
                
                # 第二行分析
                st.caption(f"{row['油門分析']} | {row['路況分析']} | 能量: {row['能量']} | 5D勝率: {row['5日勝率']} | 10D勝率: {row['10日勝率']} | {row['風險預警']} | 撤退線: {row['撤退線']}")
                st.divider()
    else:
        st.warning("⚠️ 找不到符合標的。")

# (庫存監控部分邏輯同前，請保留於原程式位置)
