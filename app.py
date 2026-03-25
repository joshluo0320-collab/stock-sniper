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
# 1. 強化名單抓取：解決「加載 0 支」的問題
# ============================================
@st.cache_data(ttl=86400)
def get_verified_stock_list_v3():
    tickers, names_map = [], {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/118.0.0.0 Safari/537.36"
    ]
    
    for url in urls:
        for _ in range(3): # 失敗重試 3 次
            try:
                res = requests.get(url, verify=False, timeout=15, headers={'User-Agent': random.choice(ua_list)})
                res.encoding = 'big5'
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'lxml')
                    for row in soup.find_all('tr'):
                        tds = row.find_all('td')
                        if len(tds) > 0:
                            raw = tds[0].text.strip().split()
                            if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                                sym = f"{raw[0]}.TW" if "strMode=2" in url else f"{raw[0]}.TWO"
                                tickers.append(sym)
                                names_map[raw[0]] = raw[1]
                    break
            except: time.sleep(1)
    
    # 備援：若官網掛了，至少分析你的核心標的
    if not tickers:
        backup = {"2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐"}
        for k, v in backup.items():
            tickers.append(f"{k}.TW")
            names_map[k] = v
            
    return tickers, names_map

# ============================================
# 2. 核心分析：白話實戰邏輯
# ============================================
def execute_master_analysis(df, tid, name, news_w, vol_gate, trail_p):
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v

    close = df['Close']
    dif = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff().iloc[-1]
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = close.iloc[-1] > high_20
    
    score = 40 + (25 if dif > 0 else -10) + (20 if is_break else 0) + (10 if v_ratio > 1.2 else 0) + news_w.get(tid, 0)
    last_p = round(float(close.iloc[-1]), 2)
    
    return {
        "股票名稱": name, "代號": tid, "綜合勝率": f"{int(min(98, score))}%",
        "氣勢分析": "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行",
        "路況分析": "🛣️ 前方無障礙" if is_break else "🚧 前方有牆",
        "能量分析": "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 油量正常",
        "今日收盤": last_p,
        "隔日進場區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "防守價": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. 執行介面：雷達動態與全自動展開
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_gate = st.sidebar.slider("🎯 勝率門檻", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

st.title("🏹 2026 全景獵殺系統 v11.0 - 獵殺雷達版")

news_w = {"2337": 15, "3017": 15, "3234": 15, "1409": 10, "4919": 10}

if st.button("🔴 啟動全台股獵殺掃描 (Top 10)", type="primary"):
    # --- 第一步：抓取名單 ---
    with st.spinner("🌐 正在連線證交所取得地圖..."):
        tickers, names_map = get_verified_stock_list_v3()
    
    if tickers:
        st.success(f"✅ 已加載 {len(tickers)} 支市場標的，開始偵測...")
        
        # --- 第二步：啟動雷達 ---
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        chunk_size = 40
        for i in range(0, len(tickers), chunk_size):
            progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
            chunk = tickers[i : i + chunk_size]
            status_text.markdown(f"📡 **掃描中:** `區段 {chunk[0][:4]}`")
            
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=20)
                for t in chunk:
                    tid = t.split(".")[0]
                    df = data[t] if len(chunk) > 1 else data
                    res = execute_master_analysis(df, tid, names_map.get(tid, tid), news_w, vol_limit, trail_pct)
                    if res and int(res['綜合勝率'].replace('%','')) >= min_gate:
                        results.append(res)
            except: continue
            
        status_text.empty()
        progress_bar.empty()
        
        # --- 第三步：自動展開結果 ---
        if results:
            st.info(f"🎯 獵殺完成！在 {len(tickers)} 支中發現 {len(results)} 支符合門檻標的。")
            df_final = pd.DataFrame(results).sort_values(by="綜合勝率", ascending=False).head(10)
            st.subheader("🏆 全台股獵殺：最強前 10 名標的")
            st.dataframe(df_final, use_container_width=True, hide_index=True)
            
            # 合夥人解析
            st.markdown("---")
            st.header("🧠 人生合夥人的盤後點醒")
            best = df_final.iloc[0]
            st.info(f"**【戰略首選：{best['股票名稱']}】**\n"
                    f"氣勢：{best['氣勢分析']} / 路況：{best['路況分析']}\n"
                    f"建議明天進場區間：**{best['隔日進場區']}**。這支標的是全市場「能量與時事」的最佳交集點。")
        else:
            st.warning("⚠️ 掃描完畢，但在目前的門檻下未發現獵物。請試著調低「勝率」或「均張」再試。")
    else:
        st.error("❌ 無法連網取得名單，請檢查連線或手動嘗試。")
