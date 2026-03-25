import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 強化名單抓取：確保 1,800+ 支完整性
# ============================================
@st.cache_data(ttl=3600)
def get_1800_market_list():
    tickers, names_map = [], {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", 
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    ]
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
    
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=20, headers={'User-Agent': ua})
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
    return tickers, names_map

# ============================================
# 2. 核心分析與白話邏輯
# ============================================
def master_sniper_logic(df, tid, name, news_w, vol_gate, trail_p):
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < vol_gate: return None # 均張門檻
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v

    close = df['Close']
    dif = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff().iloc[-1]
    is_break = close.iloc[-1] > df['High'].rolling(20).max().shift(1).iloc[-1]
    
    score = 40 + (25 if dif > 0 else -10) + (20 if is_break else 0) + (10 if v_ratio > 1.2 else 0) + news_w.get(tid, 0)
    last_p = round(float(close.iloc[-1]), 2)
    
    return {
        "名稱": name, "代號": tid, "綜合勝率": int(min(98, score)),
        "氣勢分析": "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行",
        "路況分析": "🛣️ 前方無障礙" if is_break else "🚧 前方有牆",
        "能量分析": "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 油量正常",
        "今日收盤": last_p,
        "明日進場區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "防守價": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. 執行介面
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_gate = st.sidebar.slider("🎯 勝率門檻", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落", 3.0, 15.0, 7.0)

st.title("🏹 2026 全景獵殺系統 v14.0 - 全場 1800+ 強制執行版")

if st.button("🔴 啟動全台股地毯獵殺 (1/1800+)", type="primary"):
    final_results = []
    with st.status("📡 正在全掃描台股 1,800+ 支標的...", expanded=True) as status:
        tickers, names_map = get_1800_market_list()
        
        # --- 數量驗證點 ---
        if len(tickers) < 1000:
            st.error(f"❌ 警告：僅抓取到 {len(tickers)} 支名單，未達全市場標準。請重試或檢查連線。")
        else:
            st.success(f"✅ 成功鎖定全台股 {len(tickers)} 支標的！")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            chunk_size = 50
            for i in range(0, len(tickers), chunk_size):
                progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
                chunk = tickers[i : i + chunk_size]
                status_text.markdown(f"🔍 **掃描中:** `{chunk[0][:4]}` 等 50 支...")
                try:
                    data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=30)
                    for t in chunk:
                        tid = t.split(".")[0]
                        df = data[t] if len(chunk) > 1 else data
                        res = master_sniper_logic(df, tid, names_map.get(tid, tid), {}, vol_limit, trail_pct)
                        if res and res['綜合勝率'] >= min_gate:
                            final_results.append(res)
                except: continue
            
            status.update(label=f"🎯 獵殺完成！在 {len(tickers)} 支中發現符合標的。", state="complete", expanded=False)

    if final_results:
        st.success(f"📊 報告：全市場 1/1800 掃描完畢，共 {len(final_results)} 支符合門檻。")
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        df_final['綜合勝率'] = df_final['綜合勝率'].apply(lambda x: f"{x}%")
        st.dataframe(df_final, use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ 全市場搜尋完畢，無人符合高標。請調低「勝率」或「均張」門檻。")
