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
# 1. 強化名單抓取：三層防禦機制
# ============================================
@st.cache_data(ttl=86400)
def get_verified_stock_list_v2():
    tickers, names_map = [], {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    
    # 模擬多種瀏覽器頭部，防止被封鎖
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/119.0"
    ]

    for url in urls:
        success = False
        for retry in range(3): # 最多嘗試 3 次
            try:
                headers = {'User-Agent': random.choice(user_agents)}
                res = requests.get(url, verify=False, timeout=20, headers=headers)
                res.encoding = 'big5'
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'lxml')
                    rows = soup.find_all('tr')
                    for row in rows:
                        tds = row.find_all('td')
                        if len(tds) > 0:
                            raw = tds[0].text.strip().split()
                            if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                                suffix = ".TW" if "strMode=2" in url else ".TWO"
                                sym = f"{raw[0]}{suffix}"
                                tickers.append(sym)
                                names_map[raw[0]] = raw[1]
                    success = True
                    break # 成功抓取，跳出重試迴圈
            except Exception as e:
                time.sleep(1) # 等待 1 秒後重試
        
        if not success:
            st.error(f"⚠️ 無法從 {url} 獲取名單，請確認網路或手動檢查。")

    # --- 第三層防禦：本地備援 (當全數失敗時) ---
    if not tickers:
        st.warning("📡 正在啟用本地備援核心標的名單...")
        backup = {"2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐", "2330": "台積電", "2317": "鴻海"}
        for k, v in backup.items():
            tickers.append(f"{k}.TW")
            names_map[k] = v
            
    return tickers, names_map

# ============================================
# 2. 獵殺邏輯：白話實戰分析 (保持原有強健性)
# ============================================
def master_sniper_calc(df, tid, name, news_w, vol_gate, trail_p):
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
        "明日進場區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "防守價": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. 介面執行 (帶有連線狀態顯示)
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_gate = st.sidebar.slider("🎯 勝率門檻", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落", 3.0, 15.0, 7.0)

st.title("🏹 全景獵殺系統 v8.6 - 強力防禦版")

# 模擬連網權重
news_w = {"2337": 15, "3017": 15, "3234": 15, "1409": 10, "4919": 10}

if st.button("🔴 啟動全台股獵殺掃描 (Top 10)", type="primary"):
    with st.status("📡 獵殺雷達連線中...", expanded=True) as status:
        st.write("🌐 正在連線至證交所/櫃買中心名單...")
        tickers, names_map = get_verified_stock_list_v2()
        
        if tickers:
            st.write(f"✅ 已成功鎖定 {len(tickers)} 支標的名單。")
            st.write("🔦 正在分析市場資金流向與時事加權...")
            
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            chunk_size = 40 # 加速掃描
            for i in range(0, len(tickers), chunk_size):
                chunk = tickers[i : i + chunk_size]
                current_id = chunk[0][:4]
                status_text.markdown(f"🔍 **掃描中:** `區段 {current_id} {names_map.get(current_id[:4], '')}`")
                progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
                
                try:
                    data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=20)
                    for t in chunk:
                        tid = t.split(".")[0]
                        df = data[t] if len(chunk) > 1 else data
                        res = master_sniper_calc(df, tid, names_map.get(tid, tid), news_w, vol_limit, trail_pct)
                        if res and int(res['綜合勝率'].replace('%','')) >= min_gate:
                            results.append(res)
                except:
                    continue
            
            status_text.empty()
            progress_bar.empty()
            status.update(label="🎯 獵殺掃描完成！", state="complete", expanded=False)
            
            if results:
                df_final = pd.DataFrame(results).sort_values(by="綜合勝率", ascending=False).head(10)
                st.subheader("🏆 全台股獵殺：去蕪存菁最強前 10 名")
                st.dataframe(df_final, use_container_width=True, hide_index=True)
                
                # 人生合夥人建議區
                st.markdown("---")
                st.header("🧠 人生合夥人的盤後點醒")
                best = df_final.iloc[0]
                st.info(f"**【戰術首選：{best['股票名稱']}】**\n\n"
                        f"它的**氣勢**為 {best['氣勢分析']}，**路況**為 {best['路況分析']}。\n"
                        f"能量顯示 **{best['能量分析']}**，明天建議在 **{best['明日進場區']}** 區間伏擊。")
            else:
                st.warning("⚠️ 目前條件下未發現符合門檻之獵物。")
