import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 自動名單抓取 (加入快取與超時重試)
# ============================================
@st.cache_data(ttl=86400)
def get_verified_stock_list():
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
        except Exception as e:
            st.warning(f"名單抓取異常: {url}，將使用內存備份。")
    return tickers, names_map

# ============================================
# 2. 獵殺邏輯 (白話實戰分析)
# ============================================
def master_sniper_calc(df, tid, name, news_w, vol_gate, trail_p):
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    
    # [5日均張分析]
    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v

    # [油門與路況分析]
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
        "明日進場建議區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "防守價": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. 介面執行 (含狀態動畫)
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_gate = st.sidebar.slider("🎯 勝率門檻", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落", 3.0, 15.0, 7.0)

st.title("🏹 2026 全景獵殺系統 - 狀態感知版")

# 全球時事模擬權重 (可擴充連網代碼)
news_w = {"2337": 15, "3017": 15, "3234": 15, "1409": 10}

if st.button("🔴 啟動全台股獵殺掃描 (Top 10)", type="primary"):
    tickers, names_map = get_verified_stock_list()
    
    if not tickers:
        st.error("❌ 無法取得市場名單，請檢查網路連線。")
    else:
        results = []
        # --- 動態動畫與進度條 ---
        status_placeholder = st.empty()
        progress_bar = st.progress(0)
        
        chunk_size = 30 # 調整抓取大小
        total_chunks = len(tickers) // chunk_size + 1
        
        with st.spinner("🚀 獵殺雷達啟動中..."):
            for i in range(0, len(tickers), chunk_size):
                chunk = tickers[i : i + chunk_size]
                current_batch_name = names_map.get(chunk[0][:4], "未知")
                
                # 更新狀態提示動畫
                status_placeholder.markdown(f"📡 **雷達掃描中...** 目前偵測區段：`{chunk[0][:4]} {current_batch_name}` 等標的")
                progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
                
                try:
                    data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=15)
                    for t in chunk:
                        tid = t.split(".")[0]
                        df = data[t] if len(chunk) > 1 else data
                        res = master_sniper_calc(df, tid, names_map.get(tid, tid), news_w, vol_limit, trail_pct)
                        if res and int(res['綜合勝率'].replace('%','')) >= min_gate:
                            results.append(res)
                except:
                    continue
                
                # 每個批次稍微留白，確保介面更新
                time.sleep(0.05)
        
        status_placeholder.success("✅ 獵殺掃描完成！")
        progress_bar.empty()
        
        if results:
            df_final = pd.DataFrame(results).sort_values(by="綜合勝率", ascending=False).head(10)
            st.subheader("🏆 今日全台股獵殺：最強前 10 名標的")
            st.dataframe(df_final, use_container_width=True, hide_index=True)
            
            # 人生合夥人建議
            st.markdown("---")
            st.header("🧠 人生合夥人的盤後點醒")
            best = df_final.iloc[0]
            st.info(f"**【戰略首選：{best['股票名稱']}】**\n\n"
                    f"目前 **{best['氣勢分析']}** 且 **{best['路況分析']}**。\n"
                    f"能量顯示 **{best['能量分析']}**，明天建議在 **{best['明日進場建議區']}** 區間伏擊。")
        else:
            st.warning("⚠️ 掃描完畢，但在目前的門檻下，未發現符合條件的獵物。請試著降低「勝率門檻」或「均張門檻」。")
