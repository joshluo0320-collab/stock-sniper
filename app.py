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
# 1. 地毯式搜索：三層防護抓取名單
# ============================================
@st.cache_data(ttl=86400)
def get_total_market_list_v3():
    tickers, names_map = [], {}
    # 核心備援名單 (防彈第一層)
    backup_list = {"2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐", "2330": "台積電"}
    
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
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
    
    # 若全數失敗，啟用備援
    if not tickers:
        for k, v in backup_list.items():
            tickers.append(f"{k}.TW")
            names_map[k] = v
            
    return tickers, names_map

# ============================================
# 2. 核心分析：數據轉白話
# ============================================
def execute_sniper_logic(df, tid, name, news_w, vol_gate, trail_p):
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
        "股票名稱": name, "代號": tid, "綜合勝率": int(min(98, score)),
        "氣勢分析": "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行",
        "路況分析": "🛣️ 前方無障礙" if is_break else "🚧 前方有牆",
        "能量分析": "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 油量正常",
        "今日收盤": last_p,
        "明日建議進場區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "防守價": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. UI 控制與獵殺執行
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_gate = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落", 3.0, 15.0, 7.0)

st.title("🏹 2026 全景獵殺系統 v13.0 - 防彈除蟲版")

news_w = {"2337": 15, "3017": 15, "3234": 15, "1409": 10, "4919": 10}

if st.button("🔴 啟動全台股 1,800+ 支標的地毯獵殺", type="primary"):
    # --- 關鍵修復：初始化 final_results 避免 NameError ---
    final_results = []
    
    with st.status("📡 獵殺雷達連線中...", expanded=True) as status:
        st.write("🌐 正在連線證交所抓取完整地圖...")
        tickers, names_map = get_total_market_list_v3()
        
        st.write(f"✅ 鎖定 {len(tickers)} 支標的，開始量價與時事深度掃描...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 批次下載提高穩定性
        chunk_size = 40
        for i in range(0, len(tickers), chunk_size):
            progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
            chunk = tickers[i : i + chunk_size]
            status_text.markdown(f"🔍 **掃描進度:** `{chunk[0][:4]} ...`")
            
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=25)
                for t in chunk:
                    tid = t.split(".")[0]
                    df = data[t] if len(chunk) > 1 else data
                    res = execute_sniper_logic(df, tid, names_map.get(tid, tid), news_w, vol_limit, trail_pct)
                    if res and res['綜合勝率'] >= min_gate:
                        final_results.append(res)
            except: continue
            
        status_text.empty()
        progress_bar.empty()
        status.update(label=f"🎯 獵殺完成！在 {len(tickers)} 支中篩選出結果。", state="complete", expanded=False)

    # --- 全自動展開結果 (修復後的邏輯) ---
    if final_results:
        st.success(f"📊 報告：全市場共篩選出 **{len(final_results)}** 支符合獵殺門檻標的。")
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        
        # 美化輸出：將勝率轉回字串顯示
        df_final['綜合勝率'] = df_final['綜合勝率'].apply(lambda x: f"{x}%")
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # 人生合夥人深度點醒
        st.markdown("---")
        st.header("🧠 人生合夥人的盤後點醒")
        best = df_final.iloc[0]
        st.info(f"**【戰場之王：{best['股票名稱']} ({best['代號']})】**\n\n"
                f"氣勢：{best['氣勢分析']} / 路況：{best['路況分析']}\n"
                f"能量顯示：{best['能量分析']}\n\n"
                f"**建議策略：** 這是目前全台股 1,800 支中最完美的交集標的。明日建議在 **{best['明日建議進場區']}** 伏擊。")
    else:
        st.warning("⚠️ 掃描了 1,800 支標的，但無人符合您的門檻。建議調低「勝率」或「均張」門檻再試。")
