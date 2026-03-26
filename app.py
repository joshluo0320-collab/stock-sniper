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
# 1. 核心數據獲取
# ============================================
@st.cache_data(ttl=86400)
def get_market_map():
    tickers, names_map = [], {}
    backup = {"2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐"}
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
    if not tickers:
        for k, v in backup.items(): tickers.append(f"{k}.TW"); names_map[k] = v
    return tickers, names_map

# ============================================
# 2. 獵人核心：精確計算與分析
# ============================================
def execute_sniper_v23(df, tid, name, vol_gate, trail_p, max_budget):
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    
    last_p = round(float(df['Close'].iloc[-1]), 2)
    if last_p > max_budget: return None

    # [分析指標]
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd_slope = (ema_12 - ema_26).diff().iloc[-1]
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = df['Close'].iloc[-1] > high_20
    
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    if avg_v_5 < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5
    
    inst_days = 0
    ma20 = df['Close'].rolling(20).mean()
    for i in range(1, 6):
        if df['Close'].iloc[-i] > ma20.iloc[-i]: inst_days += 1
        else: break

    win_5 = 40 + (30 if df['Close'].iloc[-1] > df['Close'].rolling(5).mean().iloc[-1] else -10)
    win_10 = 40 + (40 if macd_slope > 0 else -15)
    total_score = int((win_5 * 0.4) + (win_10 * 0.6) + (10 if is_break else 0))
    
    today_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) * 100
    risk = "⚠️ 隔日沖" if (v_ratio > 2.5 and today_ret > 7) else "✅ 穩健"

    return {
        "名稱": name, "代號": tid, "綜合勝率": total_score,
        "價格": last_p, "進場區": f"{round(last_p * 0.98, 2)}~{round(last_p * 0.995, 2)}",
        "油門": "🏎️ 加速" if macd_slope > 0 else "🐢 減速",
        "路況": "🛣️ 無壓" if is_break else "🚧 有牆",
        "能量": "⛽ 爆量" if v_ratio > 1.5 else "🚗 正常",
        "法人": f"🏛️ {inst_days}天", "風險": risk,
        "撤退線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. 介面與資金分配邏輯
# ============================================
st.set_page_config(page_title="獵殺系統 v23.0", layout="wide")
st.sidebar.header("🕹️ 獵殺控制台")
target_win = st.sidebar.slider("🎯 勝率門檻", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 止盈回落", 1.0, 15.0, 7.0, step=0.5)
max_budget = st.sidebar.number_input("💸 單張預算上限", value=250)
total_cash = st.sidebar.number_input("💰 可用總現金 (元)", value=190000)

st.title("🏹 2026 全景獵殺系統 v23.0 - 資金最大化版")

# [庫存模組省略以節省空間，邏輯同前版]

if st.button("🔴 啟動 1/1800+ 地毯式獵殺", type="primary"):
    final_results = []
    with st.status("📡 掃描全台股標的...", expanded=True) as status:
        tickers, names_map = get_market_map()
        pb = st.progress(0)
        chunk_size = 50
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            pb.progress(min((i + chunk_size) / len(tickers), 1.0))
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False)
                for t in chunk:
                    tid = t.split(".")[0]
                    df = data[t] if len(chunk) > 1 else data
                    res = execute_sniper_v23(df, tid, names_map.get(tid, tid), vol_limit, trail_pct, max_budget)
                    if res and res['綜合勝率'] >= target_win: final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺完成！", state="complete")

    if final_results:
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        st.subheader("🏆 全場最強 Top 10 名單")
        
        for _, row in df_final.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
                c1.markdown(f"### **{row['名稱']}** ({row['代號']})")
                c2.metric("勝率", f"{row['綜合勝率']}%")
                c3.metric("價格", row['價格'])
                c4.info(f"🎯 進場區: {row['進場區']}")
                st.write(f"**分析：** {row['油門']} | {row['路況']} | {row['能量']} | {row['法人']} | {row['風險']} | **撤退線: {row['撤退線']}**")
                st.divider()

        # --- 新增：人生合夥人資金分配建議 ---
        st.markdown("---")
        st.header("🧠 人生合夥人：Top 3 資金佈局建議")
        top3 = df_final.head(3)
        
        # 資金分配比率：53%, 32%, 15%
        ratios = [0.53, 0.32, 0.15]
        
        cols = st.columns(3)
        for idx, (_, stock) in enumerate(top3.iterrows()):
            suggested_money = total_cash * ratios[idx]
            suggested_shares = int((suggested_money / (stock['價格'] * 1000)))
            
            with cols[idx]:
                st.success(f"**No.{idx+1} {stock['名稱']}**")
                st.write(f"戰略地位：{'核心攻擊' if idx==0 else '趨勢護航' if idx==1 else '轉折奇兵'}")
                st.write(f"建議投入：**${int(suggested_money):,}**")
                st.write(f"建議購買：**{suggested_shares} 張**")
                st.write(f"分析：{stock['名稱']}目前{stock['油門']}且{stock['路況']}。若明日開盤守住{stock['進場區'].split('~')[0]}，即可執行火力配置。")
    else:
        st.warning("⚠️ 預算內無標的，請調整控制台參數。")
