import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 核心邏輯：v23.2 波動動能重設
# ============================================
def execute_sniper_v23(df, tid, name, vol_gate, trail_p, max_budget):
    if df.empty or len(df) < 40: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    last_p = round(float(df['Close'].iloc[-1]), 2)
    if last_p > max_budget: return None

    # ATR 波動率計算 (過濾中鋼、亞泥等牛皮股)
    tr = pd.concat([
        df['High'] - df['Low'], 
        abs(df['High'] - df['Close'].shift(1)), 
        abs(df['Low'] - df['Close'].shift(1))
    ], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean().iloc[-1]
    volatility_ratio = (atr_14 / last_p) * 100
    
    # 油門與能量
    ma5 = df['Close'].rolling(5).mean().iloc[-1]
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd_slope = (ema_12 - ema_26).diff().iloc[-1]
    
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = last_p > high_20
    
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5 if avg_v_5 > 0 else 0

    # 勝率評分 (動能導向)
    win_5 = 50 if last_p > ma5 else 0
    win_10 = 50 if macd_slope > 0 else -20
    total_score = int((win_5 * 0.4) + (win_10 * 0.6) + (10 if is_break else 0))
    
    # 動態撤退線 (3.5%~7.0%)
    dynamic_trail = min(max(trail_p, 3.5), 7.0) 
    withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - dynamic_trail/100)), 2)

    return {
        "名稱": name, "代號": tid, "綜合勝率": total_score,
        "價格": last_p, "波動力": f"{round(volatility_ratio, 2)}%",
        "油門": "🏎️ 加速" if macd_slope > 0 else "🐢 減速",
        "路況": "🛣️ 無壓" if is_break else "🚧 有牆",
        "能量": "⛽ 爆量" if v_ratio > 1.5 else "🚗 正常",
        "撤退線": withdrawal_line, "ATR": volatility_ratio,
        "進場區": f"{round(last_p * 0.98, 2)}~{round(last_p * 0.995, 2)}"
    }

# ============================================
# 2. 名單抓取與工具
# ============================================
@st.cache_data(ttl=86400)
def get_market_map():
    tickers, names_map = [], {}
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=10)
            res.encoding = 'big5'
            soup = BeautifulSoup(res.text, 'lxml')
            for row in soup.find_all('tr'):
                tds = row.find_all('td')
                if len(tds) > 0:
                    raw = tds[0].text.strip().split()
                    if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                        suffix = ".TW" if "strMode=2" in url else ".TWO"
                        tickers.append(f"{raw[0]}{suffix}"); names_map[raw[0]] = raw[1]
        except: continue
    return tickers, names_map

# ============================================
# 3. Streamlit UI
# ============================================
st.set_page_config(page_title="獵殺系統 v23.2", layout="wide")
st.sidebar.header("🕹️ 獵殺控制台")
target_win = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 15.0, 5.0)
max_budget = st.sidebar.number_input("💸 單張預算上限 (元)", value=250)
total_cash = st.sidebar.number_input("💰 可用總現金 (元)", value=190000)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控 (代號,成本)\n例如: 2337,34", value="2337,34")

st.title("🏹 2026 獵殺系統 v23.2 - 完整版")

# --- A. 庫存檢視模組 (修復歸來) ---
st.subheader("📊 庫藏動態與撤退點醒")
if st.button("🔄 刷新庫存狀態"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_res = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="6mo", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="6mo", progress=False)
        # 庫存分析不受預算與波動率過濾限制
        res = execute_sniper_v23(df, tid, tid, 0, trail_pct, 9999)
        if res:
            p_l = (res['價格'] / float(cost) - 1) * 100
            inv_res.append({
                "代號": tid, "現價": res['價格'], "盈虧": f"{round(p_l, 2)}%",
                "撤退線": res['撤退線'], "狀態": res['油門'], "波動力": res['波動力'],
                "決策建議": "✅ 趨勢強續留" if res['價格'] > res['撤退線'] else "⚠️ 觸發斷捨離"
            })
    if inv_res: st.table(pd.DataFrame(inv_res))
    else: st.info("請在側邊欄輸入正確的庫存資訊。")

st.markdown("---")

# --- B. 全市場獵殺 ---
if st.button("🔴 啟動全台股地毯獵殺", type="primary"):
    final_results = []
    tickers, names_map = get_market_map()
    with st.status("📡 掃描中...", expanded=True) as status:
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
                    # 執行波動率過濾：ATR < 1.5% 踢除
                    if res and res['ATR'] >= 1.5 and res['綜合勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺完成！", state="complete")

    if final_results:
        st.subheader("🏆 v23.2 精選動能標的")
        st.table(pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10))
    else:
        st.warning("⚠️ 目前無標的符合波動動能門檻。")
