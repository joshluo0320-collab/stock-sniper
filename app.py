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
# 1. 地毯式搜索：確保 1,800+ 支名單完整加載
# ============================================
@st.cache_data(ttl=86400)
def get_total_market_list():
    tickers, names_map = [], {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市 (約 1000 支)
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃 (約 800 支)
    ]
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36"
    ]
    
    for url in urls:
        success = False
        for _ in range(3): # 失敗自動重試 3 次
            try:
                headers = {'User-Agent': random.choice(ua_list)}
                res = requests.get(url, verify=False, timeout=20, headers=headers)
                res.encoding = 'big5'
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'lxml')
                    rows = soup.find_all('tr')
                    for row in rows:
                        tds = row.find_all('td')
                        if len(tds) > 0:
                            raw = tds[0].text.strip().split()
                            # 嚴格篩選：必須是 4 位數代碼（排除權證、存託憑證等）
                            if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                                suffix = ".TW" if "strMode=2" in url else ".TWO"
                                sym = f"{raw[0]}{suffix}"
                                tickers.append(sym)
                                names_map[raw[0]] = raw[1]
                    success = True
                    break
            except: time.sleep(1)
        if not success:
            st.warning(f"⚠️ 無法取得部分名單 ({url})，請檢查網路。")
            
    return tickers, names_map

# ============================================
# 2. 核心獵殺邏輯：將數據轉化為白話決策
# ============================================
def execute_sniper_logic(df, tid, name, news_w, vol_gate, trail_p):
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    # [能量分析]
    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < vol_gate: return None # 均張過濾
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v

    # [趨勢與路況]
    close = df['Close']
    dif = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff().iloc[-1]
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = close.iloc[-1] > high_20
    
    # [綜合勝率]
    score = 40 + (25 if dif > 0 else -10) + (20 if is_break else 0) + (10 if v_ratio > 1.2 else 0) + news_w.get(tid, 0)
    last_p = round(float(close.iloc[-1]), 2)
    
    return {
        "股票名稱": name, "代號": tid, "綜合勝率": f"{int(min(98, score))}%",
        "氣勢分析": "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行",
        "路況分析": "🛣️ 前方無障礙" if is_break else "🚧 前方有牆",
        "能量分析": "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 油量正常",
        "今日收盤": last_p,
        "明日建議進場區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "防守撤退線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. UI 控制與獵殺雷達
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_gate = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

st.title("🏹 全景獵殺系統 v12.0 - 1,800+ 地毯搜索版")

# 時事權重 (2026/03/26 熱點)
news_w = {"2337": 15, "3017": 15, "3234": 15, "1409": 10, "4919": 10}

if st.button("🔴 啟動全台股地毯式獵殺 (Top 10)", type="primary"):
    with st.status("📡 獵殺雷達啟動中...", expanded=True) as status:
        st.write("🌐 正在連線證交所抓取完整地圖...")
        tickers, names_map = get_total_market_list()
        
        if not tickers:
            st.error("❌ 無法取得名單，連線被阻斷。")
        else:
            st.write(f"✅ 已成功鎖定 **{len(tickers)}** 支台股標的！")
            st.write("🔦 正在進行全市場量價掃描與 AI 權重計算...")
            
            final_results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 批次下載 (每 50 支一組)，兼顧速度與穩定性
            chunk_size = 50
            for i in range(0, len(tickers), chunk_size):
                chunk = tickers[i : i + chunk_size]
                progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
                status_text.markdown(f"🔍 **掃描進度:** `{chunk[0][:4]} ~ {chunk[-1][:4]}`")
                
                try:
                    data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=25)
                    for t in chunk:
                        tid = t.split(".")[0]
                        df = data[t] if len(chunk) > 1 else data
                        res = execute_sniper_logic(df, tid, names_map.get(tid, tid), news_w, vol_limit, trail_pct)
                        if res and int(res['綜合勝率'].replace('%','')) >= min_gate:
                            final_results.append(res)
                except: continue
                time.sleep(0.05)
            
            status_text.empty()
            progress_bar.empty()
            status.update(label=f"🎯 獵殺完成！在 {len(tickers)} 支中篩選出符合條件標的。", state="complete", expanded=False)

    # --- 全自動展開結果 ---
    if final_results:
        st.success(f"📊 報告：全市場共篩選出 **{len(final_results)}** 支符合獵殺門檻之精銳。")
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        st.subheader("🏆 全台股最強前 10 名（全自動展開）")
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # 人生合夥人點醒
        st.markdown("---")
        st.header("🧠 人生合夥人的盤後點醒")
        best = df_final.iloc[0]
        st.info(f"**【當前最強：{best['股票名稱']} ({best['代號']})】**\n\n"
                f"氣勢：{best['氣勢分析']} / 路況：{best['路況分析']}\n"
                f"能量顯示：{best['能量分析']}\n\n"
                f"**獵人建議：** 這支標的是目前 1,800 支台股中，動能與趨勢最完美的交集。建議明日於 **{best['明日建議進場區']}** 伏擊。")
    else:
        st.warning(f"⚠️ 掃描了 {len(tickers)} 支標的，但無人符合您的門檻 (勝率 {min_gate}% / 均張 {vol_limit})。")
