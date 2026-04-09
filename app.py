import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 名單獲取 (全市場 1,800+ 備援機制)
# ============================================
@st.cache_data(ttl=86400)
def get_market_map():
    tickers, names_map = [], {}
    backup = {"2337": "旺宏", "1449": "佳和", "2351": "順德", "6693": "廣閎科"}
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
# 2. 獵人核心：v23.2 波動率過濾邏輯
# ============================================
def execute_sniper_v23(df, tid, name, vol_gate, trail_p, max_budget):
    if df.empty or len(df) < 40: return None
    
    # 強制修正 yfinance 可能產生的 MultiIndex 問題
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    last_p = round(float(df['Close'].iloc[-1]), 2)
    if last_p > max_budget: return None

    # --- [修正核心 1：加入波動率過濾 ATR] ---
    # 這是為了踢掉中鋼、亞泥等牛皮股
    tr = pd.concat([
        df['High'] - df['Low'], 
        abs(df['High'] - df['Close'].shift(1)), 
        abs(df['Low'] - df['Close'].shift(1))
    ], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean().iloc[-1]
    volatility_ratio = (atr_14 / last_p) * 100
    
    # 門檻：波動率低於 1.5% 的標的視為無效獵物
    if volatility_ratio < 1.5: return None 

    # --- [修正核心 2：動態油門與能量] ---
    ma5 = df['Close'].rolling(5).mean().iloc[-1]
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd_slope = (ema_12 - ema_26).diff().iloc[-1]
    
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = last_p > high_20
    
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    if avg_v_5 < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5

    # --- [修正核心 3：勝率計算與撤退線] ---
    win_5 = 50 if last_p > ma5 else 0
    win_10 = 50 if macd_slope > 0 else -20
    total_score = int((win_5 * 0.4) + (win_10 * 0.6) + (10 if is_break else 0))
    
    today_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) * 100
    risk = "⚠️ 隔日沖" if (v_ratio > 3.0 and today_ret > 6) else "✅ 穩健"

    # 撤退線修正：使用動態回落
    dynamic_trail = min(max(trail_p, 3.5), 7.0) 
    withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - dynamic_trail/100)), 2)

    return {
        "名稱": name, "代號": tid, "綜合勝率": total_score,
        "價格": last_p, "波動力": f"{round(volatility_ratio, 2)}%",
        "油門": "🏎️ 加速" if macd_slope > 0 else "🐢 減速",
        "路況": "🛣️ 無壓" if is_break else "🚧 有牆",
        "能量": "⛽ 爆量" if v_ratio > 1.5 else "🚗 正常",
        "風險": risk, "撤退線": withdrawal_line,
        "進場區": f"{round(last_p * 0.98, 2)}~{round(last_p * 0.995, 2)}"
    }

# ============================================
# 3. UI 介面與顯示
# ============================================
st.set_page_config(page_title="獵殺系統 v23.2", layout="wide")
st.sidebar.header("🕹️ 獵殺控制台 (v23.2 重設版)")
target_win = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 15.0, 5.0, step=0.5)
max_budget = st.sidebar.number_input("💸 單張上限 (元)", value=250)
total_cash = st.sidebar.number_input("💰 可用總現金 (元)", value=190000)

st.title("🏹 2026 獵殺系統 v23.2 - 波動動能重設版")

if st.button("🔴 啟動全市場動能獵殺", type="primary"):
    final_results = []
    tickers, names_map = get_market_map()
    
    with st.status("📡 搜尋符合波動率 > 1.5% 之獵物...", expanded=True) as status:
        pb = st.progress(0)
        chunk_size = 50
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            pb.progress(min((i + chunk_size) / len(tickers), 1.0))
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False)
                for t in chunk:
                    tid = t.split(".")[0]
                    # 處理單一或多個股票的 dataframe 結構
                    df = data[t] if len(chunk) > 1 else data
                    res = execute_sniper_v23(df, tid, names_map.get(tid, tid), vol_limit, trail_pct, max_budget)
                    if res and res['綜合勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺篩選完成！", state="complete")

    if final_results:
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        st.subheader("🏆 v23.2 精選動能標的 (已過濾牛皮股)")
        st.table(df_final)
    else:
        st.warning("⚠️ 目前市場標的均不符合波動動能門檻，請維持空倉。")
