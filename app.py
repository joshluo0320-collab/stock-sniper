import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 全市場清單抓取模組 (上市+上櫃)
# ============================================
@st.cache_data(ttl=86400) # 每天更新一次名單即可
def get_all_taiwan_stock_tickers():
    """自動從證交所抓取全市場 1,800+ 支標的與中文名稱"""
    tickers = []
    names_map = {}
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
                    text = tds[0].text.strip().split()
                    if len(text) >= 2 and len(text[0]) == 4 and text[0].isdigit():
                        symbol = f"{text[0]}.TW" if "strMode=2" in url else f"{text[0]}.TWO"
                        tickers.append(symbol)
                        names_map[text[0]] = text[1] # 存入中文名
        except: continue
    return tickers, names_map

# ============================================
# 2. 自動連網：時事與國際情勢權重
# ============================================
@st.cache_data(ttl=3600)
def get_live_sentiment():
    weights = {} # 全市場掃描時，由關鍵字觸發加分
    try:
        res = requests.get("https://money.udn.com/money/index", timeout=5, verify=False)
        res.encoding = 'utf-8'
        text = res.text
        # 如果新聞提到關鍵產業，該族群代號區間加分 (範例)
        if "記憶體" in text: weights.update({"2337": 15, "2408": 10, "3260": 10})
        if "散熱" in text: weights.update({"3017": 15, "3324": 15, "3338": 15})
        if "矽光子" in text: weights.update({"3234": 15, "4979": 10})
        if "衝突" in text or "避險" in text: weights.update({"1409": 15, "2104": 10})
    except: pass
    return weights

# ============================================
# 3. 核心邏輯：白話分析與勝率計算
# ============================================
def master_sniper_logic(df, tid, name, news_w, vol_gate):
    if df.empty or len(df) < 25: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    # [能量：油箱]
    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v

    # [趨勢：油門]
    close = df['Close']
    dif = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff().iloc[-1]
    
    # [突破：牆壁]
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = close.iloc[-1] > high_20
    
    # [綜合勝率]
    score = 40 + (25 if dif > 0 else -10) + (20 if is_break else 0) + (10 if v_ratio > 1.2 else 0) + news_w.get(tid, 0)
    
    last_p = round(float(close.iloc[-1]), 2)
    return {
        "股票名稱": name, "代號": tid, "綜合勝率": f"{min(98, score)}%",
        "氣勢分析": "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行",
        "路況分析": "🛣️ 前方無障礙" if is_break else "🚧 前方有牆",
        "能量分析": "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 油量正常",
        "今日收盤": last_p,
        "隔日建議進場區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "撤退防守線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_pct/100)), 2)
    }

# ============================================
# 4. UI 執行：全市場獵殺
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_score = st.sidebar.slider("🎯 勝率門檻", 10, 95, 60)
vol_gate = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

st.title("🏹 2026 全景獵殺系統 - 全台股掃描版")

if st.button("🔴 啟動全台股 1,800 支標的自動獵殺", type="primary"):
    all_tickers, names_map = get_all_taiwan_stock_tickers()
    news_w = get_live_sentiment()
    
    st.write(f"🔍 已成功加載 **{len(all_tickers)}** 支全市場標的，開始掃描...")
    
    scan_results = []
    progress_bar = st.progress(0)
    
    # 這裡使用批次下載 (每 50 支一組) 以提高效率
    chunk_size = 50
    for i in range(0, len(all_tickers), chunk_size):
        progress_bar.progress(min((i + chunk_size) / len(all_tickers), 1.0))
        chunk = all_tickers[i:i + chunk_size]
        try:
            data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=10)
            for t in chunk:
                tid = t.split(".")[0]
                df = data[t] if len(chunk) > 1 else data
                res = master_sniper_logic(df, tid, names_map.get(tid, tid), news_w, vol_gate)
                if res and int(res['綜合勝率'].replace('%','')) >= min_score:
                    scan_results.append(res)
        except: continue
    
    if scan_results:
        df_top10 = pd.DataFrame(scan_results).sort_values(by="綜合勝率", ascending=False).head(10)
        st.subheader("🏆 全台股獵殺：最強前 10 名標的")
        st.dataframe(df_top10, use_container_width=True, hide_index=True)
        
        # 人生合夥人點醒
        st.info(f"**【合夥人點醒】** 目前全市場最強的是 **{df_top10.iloc[0]['股票名稱']}**。注意：全市場掃描能幫你發現平時沒注意的飆股，請務必確認其「隔日建議進場區」再行動。")
