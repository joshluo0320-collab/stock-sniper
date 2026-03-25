import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 戰略核心：自動抓取全市場 1,800+ 支標的
# ============================================
@st.cache_data(ttl=86400) # 每天更新一次名單
def get_total_market_list():
    """從證交所抓取上市與上櫃完整名單"""
    tickers, names_map = [], {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=20)
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
# 2. 自動連網：時事與國際情勢權重更新
# ============================================
@st.cache_data(ttl=3600)
def get_realtime_news_weights():
    """自動偵測今日熱點關鍵字加權"""
    weights = {} 
    try:
        res = requests.get("https://money.udn.com/money/index", timeout=5, verify=False)
        res.encoding = 'utf-8'
        text = res.text
        # 自動識別時事關鍵字並對特定代號加權
        if "記憶體" in text: weights.update({"2337": 15, "2408": 10})
        if "散熱" in text: weights.update({"3017": 15, "3324": 15})
        if "衝突" in text: weights.update({"1409": 15, "2104": 10})
    except: pass
    return weights

# ============================================
# 3. 核心分析：將專業數據轉化為白話建議
# ============================================
def execute_sniper_analysis(df, tid, name, news_w, vol_gate, trail_p):
    if df.empty or len(df) < 25: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()

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
    
    # [綜合勝率計算]
    score = 40 + (25 if dif > 0 else -10) + (20 if is_break else 0) + (10 if v_ratio > 1.2 else 0) + news_w.get(tid, 0)
    
    last_p = round(float(close.iloc[-1]), 2)
    return {
        "股票名稱": name, "代號": tid, "綜合勝率": f"{min(98, int(score))}%",
        "氣勢分析": "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行",
        "路況分析": "🛣️ 前方無障礙" if is_break else "🚧 前方有牆",
        "能量分析": "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 油量正常",
        "今日收盤": last_p,
        "明日建議進場區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "防守撤退線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 4. 介面佈局與全市場執行
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_gate = st.sidebar.slider("🎯 綜合勝率門檻 (%)", 10, 95, 65)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控: 代號,成本", value="2337,34\n1409,16.5")

st.title("🏹 2026 全景獵殺系統 - 1,800+ 全台股版")

news_w = get_realtime_news_weights()

# --- A. 庫存監控區 ---
if st.button("🔄 刷新庫存狀態與防守線"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_res = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="1y", progress=False)
        res = execute_sniper_analysis(df, tid, tid, news_w, 0, trail_pct)
        if res:
            p_l = (res['今日收盤'] / float(cost) - 1) * 100
            inv_res.append({
                "代號": tid, "現價": res['今日收盤'], "盈虧": f"{round(p_l, 2)}%",
                "防守價": res['防守撤退線'], "建議": "✅ 續留" if res['今日收盤'] > res['防守撤退線'] else "⚠️ 斷捨離"
            })
    st.table(inv_res)

# --- B. 全市場獵殺區 ---
if st.button("🔴 啟動全台股 1,800 支標的獵殺 (Top 10)", type="primary"):
    all_tickers, names_map = get_total_market_list()
    st.write(f"🔍 已成功加載 **{len(all_tickers)}** 支全市場標的，開始深度掃描...")
    
    final_results = []
    pb = st.progress(0)
    status_text = st.empty()
    
    # 批次處理 (每 40 支一組) 以提高效率並防止超時
    chunk_size = 40
    for i in range(0, len(all_tickers), chunk_size):
        pb.progress(min((i + chunk_size) / len(all_tickers), 1.0))
        chunk = all_tickers[i : i + chunk_size]
        status_text.text(f"📡 目前偵測區段: {chunk[0][:4]} ...")
        
        try:
            data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=25)
            for t in chunk:
                tid = t.split(".")[0]
                df = data[t] if len(chunk) > 1 else data
                res = execute_sniper_analysis(df, tid, names_map.get(tid, tid), news_w, vol_limit, trail_pct)
                if res and int(res['綜合勝率'].replace('%','')) >= min_gate:
                    final_results.append(res)
        except: continue
        time.sleep(0.05) # 微秒延遲防止連線過載

    status_text.empty()
    pb.empty()
    st.success(f"🎯 掃描完成！在 {len(all_tickers)} 支中篩選出 {len(final_results)} 支符合門檻標的。")

    if final_results:
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        st.subheader("🏆 每日前 10 名最強獵物清單")
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # --- 人生合夥人深度解析 ---
        st.markdown("---")
        st.header("🧠 人生合夥人的盤後點醒")
        best = df_final.iloc[0]
        st.info(f"**【戰略首選：{best['股票名稱']}】**\n\n"
                f"目前氣勢：{best['氣勢分析']} / 路況：{best['路況分析']}\n"
                f"能量顯示：{best['能量分析']}\n\n"
                f"**隔日佈局：** 建議進場區間為 **{best['明日建議進場區']}**。這支標的是目前全市場「勝率模型」跑出來的頂尖個案。")
    else:
        st.warning("⚠️ 掃描完畢，未發現符合高門檻之標的。請適度調低「勝率」或「均張」門檻再試。")
