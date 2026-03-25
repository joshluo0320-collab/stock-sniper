import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 戰略核心：自動抓取全市場名單
# ============================================
@st.cache_data(ttl=86400)
def get_all_stock_list():
    """從證交所抓取最新名單，並過濾出 4 位數代碼的股票"""
    tickers, names_map = [], {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=15)
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
                        names_map[raw[0]] = raw[1]
        except: continue
    return tickers, names_map

# ============================================
# 2. 自動連網：時事關鍵字權重
# ============================================
@st.cache_data(ttl=3600)
def get_live_news_weights():
    weights = {"2337": 15, "3017": 15, "3234": 15, "4919": 10, "1409": 10}
    try:
        res = requests.get("https://money.udn.com/money/index", timeout=5, verify=False)
        res.encoding = 'utf-8'
        text = res.text
        if "記憶體" in text: weights["2337"] += 10
        if "散熱" in text: weights["3017"] += 10
        if "矽光子" in text: weights["3234"] += 10
        if "避險" in text: weights["1409"] += 15
    except: pass
    return weights

# ============================================
# 3. 核心分析邏輯 (白話翻譯版)
# ============================================
def analyze_logic(df, tid, name, news_w, vol_gate, trail_p):
    if df.empty or len(df) < 20: return None
    
    # 統一欄位格式
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    if df.empty: return None

    # [能量數據]
    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v

    # [趨勢數據]
    close = df['Close']
    dif = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff().iloc[-1]
    
    # [路況數據]
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = close.iloc[-1] > high_20
    
    # [勝率計算]
    score = 40 + (25 if dif > 0 else -10) + (20 if is_break else 0) + (10 if v_ratio > 1.2 else 0) + news_w.get(tid, 0)
    
    last_p = round(float(close.iloc[-1]), 2)
    return {
        "股票名稱": name, "代號": tid, "綜合勝率": f"{min(98, score)}%",
        "氣勢分析": "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行",
        "路況分析": "🛣️ 前方無障礙" if is_break else "🚧 前方有牆",
        "能量分析": "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 油量正常",
        "今日收盤": last_p,
        "明日建議進場價": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "撤退防守線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 4. 介面執行
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_gate = st.sidebar.slider("🎯 勝率門檻", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

inventory_input = st.sidebar.text_area("📋 庫存: 代號,成本", value="2337,34\n1409,16.5")

st.title("🏹 2026 全景獵殺系統 v8.0 - DEBUG 優化版")

news_w = get_live_news_weights()

# --- 庫存監控 ---
if st.button("🔄 刷新庫存狀態"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_res = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="1y", progress=False)
        res = analyze_logic(df, tid, tid, news_w, 0, trail_pct)
        if res:
            p_l = (res['今日收盤'] / float(cost) - 1) * 100
            inv_res.append({
                "代號": tid, "現價": res['今日收盤'], "盈虧": f"{round(p_l, 2)}%",
                "防守價": res['撤退防守線'], "建議": "✅ 續留" if res['今日收盤'] > res['撤退防守線'] else "⚠️ 斷捨離"
            })
    st.table(inv_res)

# --- 全市場獵殺 ---
if st.button("🔴 啟動全台股 1,800 支標的獵殺 (Top 10)", type="primary"):
    all_tickers, names_map = get_all_stock_list()
    st.write(f"🔍 正在獵殺台股 **{len(all_tickers)}** 支標的...")
    
    final_results = []
    pb = st.progress(0)
    
    # 改用小批次，每 25 支抓一次，降低卡死機率
    chunk_size = 25
    for i in range(0, len(all_tickers), chunk_size):
        pb.progress(min((i + chunk_size) / len(all_tickers), 1.0))
        chunk = all_tickers[i : i + chunk_size]
        try:
            # 加入 timeout 避免無限等待
            data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=20)
            for t in chunk:
                tid = t.split(".")[0]
                df = data[t] if len(chunk) > 1 else data
                res = analyze_logic(df, tid, names_map.get(tid, tid), news_w, vol_limit, trail_pct)
                if res and int(res['綜合勝率'].replace('%','')) >= min_gate:
                    final_results.append(res)
        except: continue
        time.sleep(0.1) # 稍微喘息，避免被封 IP
    
    pb.empty()
    if final_results:
        df_top10 = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        st.subheader("🏆 全台股獵殺：去蕪存菁最強前 10 名")
        st.dataframe(df_top10, use_container_width=True, hide_index=True)
        
        # 人生合夥人點醒
        st.markdown("---")
        st.header("🧠 人生合夥人的盤後點醒")
        top_name = df_top10.iloc[0]['股票名稱']
        st.info(f"**【獵殺標的：{top_name}】** 是目前全市場最符合獵人直覺的標的。\n\n" + 
                f"它的**氣勢分析**為 {df_top10.iloc[0]['氣勢分析']}，代表油門已踩死；\n" +
                f"**路況分析**為 {df_top10.iloc[0]['路況分析']}，代表前面沒阻礙。\n" +
                f"建議明天在 **{df_top10.iloc[0]['明日建議進場價']}** 埋伏。")
