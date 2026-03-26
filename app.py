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
# 1. 名單獲取：三層防線（確保不為 0 支）
# ============================================
@st.cache_data(ttl=86400)
def get_verified_list():
    tickers, names_map = [], {}
    backup = {"2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐", "2330": "台積電", "1513": "中興電"}
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    
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
        st.warning("📡 啟動戰略備援名單模式")
        for k, v in backup.items():
            tickers.append(f"{k}.TW")
            names_map[k] = v
    return tickers, names_map

# ============================================
# 2. 獵人核心邏輯：法人、隔日沖、多週期勝率
# ============================================
def execute_master_logic(df, tid, name, vol_gate, trail_p, max_budget):
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    
    last_p = round(float(df['Close'].iloc[-1]), 2)
    if last_p > max_budget: return None

    # [技術因子]
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd_slope = (ema_12 - ema_26).diff().iloc[-1]
    
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    if avg_v_5 < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5

    # [勝率計算]
    win_5 = 40 + (30 if df['Close'].iloc[-1] > df['Close'].rolling(5).mean().iloc[-1] else -10)
    win_10 = 40 + (40 if macd_slope > 0 else -15)
    
    # [新增：隔日沖風險預警]
    today_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) * 100
    is_day_trade = v_ratio > 2.5 and today_ret > 7
    
    # [新增：法人動能模擬]
    inst_support = (df['Close'].tail(5) > df['Close'].rolling(20).mean().tail(5)).all()

    total_score = int((win_5 * 0.4) + (win_10 * 0.6))
    if inst_support: total_score += 10
    if is_day_trade: total_score -= 15
    
    return {
        "名稱": name, "代號": tid, "價格": last_p,
        "5日勝率": f"{min(98, int(win_5))}%",
        "10日勝率": f"{min(98, int(win_10))}%",
        "綜合勝率": int(min(98, total_score)),
        "屬性": "🏛️ 法人盤" if inst_support else "🏹 散戶盤",
        "警告": "⚠️ 隔日沖風險" if is_day_trade else "✅ 籌碼穩",
        "進場區": f"{round(last_p * 0.98, 2)}~{round(last_p * 0.995, 2)}",
        "撤退線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. UI 控制台與執行
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
target_win = st.sidebar.slider("🎯 綜合勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 1.0, 15.0, 7.0, step=0.5)
max_budget = st.sidebar.number_input("💸 單張最高預算 (元)", value=250)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控 (代號,成本)", value="2337,34\n1409,16.5")

st.title("🏹 2026 全景獵殺系統 v22.1 - 穩定版")

# --- A. 庫存監控 ---
if st.button("🔄 刷新庫存與止盈建議"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_res = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="1y", progress=False)
        res = execute_master_logic(df, tid, tid, 0, trail_pct, 9999)
        if res:
            p_l = (res['價格'] / float(cost) - 1) * 100
            inv_res.append({
                "名稱": res['名稱'], "現價": res['價格'], "盈虧": f"{round(p_l, 2)}%",
                "撤退線": res['撤退線'], "行動": "✅ 續留" if res['價格'] > res['撤退線'] else "⚠️ 斷捨離"
            })
    if inv_res: st.table(inv_res)

st.markdown("---")

# --- B. 全市場獵殺 ---
if st.button("🔴 啟動全台股地毯獵殺 (1/1800+)", type="primary"):
    final_results = [] # 初始化，防 NameError
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
                    if res and res['綜合勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺完成！", state="complete")

    if final_results:
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        st.subheader(f"🏆 預算 {max_budget} 元內最強獵物")
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # --- C. 合夥人建議 ---
        st.markdown("---")
        st.header("🧠 人生合夥人的盤後點醒")
        best = df_final.iloc[0]
        st.info(f"**【戰略首選：{best['名稱']}】**\n\n"
                f"**數據解析：** 綜合勝率 {best['綜合勝率']}%，屬性為 {best['屬性']}。\n"
                f"**風險警示：** 該標目前 {best['警告']}。若有隔日沖風險，明日開盤應觀察 30 分鐘，不破底再考慮配置你的 **19 萬現金**。")
    else:
        st.warning("⚠️ 找不到符合條件標的，建議調低門檻。")
