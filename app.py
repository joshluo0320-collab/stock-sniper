import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統設定
# ============================================
st.set_page_config(page_title="台股決賽輪 - 斷捨離實戰版", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
min_p10_threshold = st.sidebar.slider("📈 10日趨勢門檻", 5, 95, 40)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)
min_vol_lots = st.sidebar.slider("🌊 流動性門檻 (5日均張)", 0, 3000, 500)

st.sidebar.markdown("---")
st.sidebar.header("📋 當前持倉紀錄")
st.sidebar.info("若有買進，請在此輸入。系統將連動最新走勢判斷去留。")
inventory_input = st.sidebar.text_area("格式: 代號,成本 (每行一筆)", value="2337,34\n1409,16.5")

# ============================================
# 2. 核心邏輯模組
# ============================================
@st.cache_data(ttl=600) # 每10分鐘更新一次名單
def get_fresh_market_list():
    """從證交所/櫃買中心抓取最新完整名單"""
    tickers, names_map = [], {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
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
                        sym = f"{raw[0]}{suffix}"
                        tickers.append(sym)
                        names_map[sym] = raw[1]
        except: continue
    return tickers, names_map

def analyze_stock(df, tp_pct, vol_limit=0):
    """核心分析與流動性判斷"""
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    
    # 流動性檢查 (庫存檢查時 vol_limit 會設為 0)
    avg_v = df['Volume'].rolling(5).mean().iloc[-1] / 1000
    if avg_v < vol_limit: return None

    # 技術指標
    close = df['Close']
    df['MACD_S'] = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    return df

# ============================================
# 3. 介面執行區
# ============================================
st.title("🏹 台股即時獵殺：保持空杯，隨時重新開始")

# --- 區塊一：持倉動態判斷 (連動最新走勢) ---
st.subheader("📊 持倉動態即時監控")
if st.button("🔄 檢查持倉狀態 (連動最新走勢)"):
    inv_items = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    if inv_items:
        check_results = []
        for tid, cost in inv_items:
            tid = tid.strip()
            # 優先嘗試上市，不行則嘗試上櫃
            df = yf.download(f"{tid}.TW", period="1y", progress=False)
            if df.empty: df = yf.download(f"{tid}.TWO", period="1y", progress=False)
            
            if not df.empty:
                df_p = analyze_stock(df, trail_percent, 0) # 持倉不限流動性
                last_p = float(df_p['Close'].iloc[-1])
                stop_p = float(df_p['Trailing_Stop_Line'].iloc[-1])
                p_l = (last_p / float(cost) - 1) * 100
                check_results.append({
                    "代號": tid, "成本": cost, "現價": round(last_p, 2),
                    "即時損益": f"{round(p_l, 2)}%",
                    "動態止盈線": round(stop_p, 2),
                    "決策判斷": "✅ 續留" if last_p >= stop_p else "⚠️ 建議撤退"
                })
        st.table(pd.DataFrame(check_results))
    else:
        st.info("目前無持倉紀錄。")

st.markdown("---")

# --- 區塊二：全新全市場掃描 ---
st.subheader(f"🔍 全市場獵殺 (排除低於 {min_vol_lots} 張之標的)")
if st.button("🔴 開始全新的搜尋 (不綁定任何舊標的)", type="primary"):
    all_tickers, names_map = get_fresh_market_list()
    st.write(f"正在重新掃描台股 **{len(all_tickers)}** 支標的...")
    
    scan_res = []
    pb = st.progress(0)
    chunks = [all_tickers[i:i + 60] for i in range(0, len(all_tickers), 60)]
    
    for i, chunk in enumerate(chunks):
        pb.progress((i + 1) / len(chunks))
        try:
            data = yf.download(chunk, period="5mo", group_by='ticker', progress=False)
            for t in chunk:
                df_raw = data[t] if len(chunk) > 1 else data
                df_p = analyze_stock(df_raw, trail_percent, min_vol_lots)
                if df_p is not None:
                    last = df_p.iloc[-1]
                    p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (20 if last['Close'] > last['High20'] else 0)
                    if p10 >= min_p10_threshold:
                        scan_res.append({
                            "代號": t.split(".")[0], "名稱": names_map.get(t, "未知"),
                            "趨勢強度": f"{int(p10)}%", "現價": round(float(last['Close']), 2),
                            "5日均張": int(df_raw['Volume'].rolling(5).mean().iloc[-1] / 1000),
                            "撤退防守線": round(float(last['Trailing_Stop_Line']), 2)
                        })
        except: continue
    
    pb.empty()
    if scan_res:
        st.dataframe(pd.DataFrame(scan_res).sort_values(by="趨勢強度", ascending=False), hide_index=True)
    else:
        st.warning("當前盤勢尚未發現符合條件的獵物。")
