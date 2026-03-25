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
# 1. 強化版名單獲取模組 (三層保險)
# ============================================
@st.cache_data(ttl=3600)
def get_1800_market_list_armored():
    tickers, names_map = [], {}
    
    # [第三層防禦：內建核心標的備援] 
    core_backup = {
        "2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐",
        "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2383": "台光電", "3037": "欣興",
        "2376": "技嘉", "2357": "華碩", "2408": "南亞科", "2603": "長榮", "2609": "陽明"
    }

    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", 
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    ]
    
    # 模擬各種真實瀏覽器
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15"
    ]

    for url in urls:
        success = False
        for _ in range(2): # 每個 URL 嘗試 2 次
            try:
                headers = {'User-Agent': random.choice(uas)}
                res = requests.get(url, verify=False, timeout=10, headers=headers)
                res.encoding = 'big5'
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'lxml')
                    for row in soup.find_all('tr'):
                        tds = row.find_all('td')
                        if len(tds) > 0:
                            raw = tds[0].text.strip().split()
                            if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                                suffix = ".TW" if "strMode=2" in url else ".TWO"
                                tickers.append(f"{raw[0]}{suffix}")
                                names_map[raw[0]] = raw[1]
                    success = True
                    break
            except:
                time.sleep(1)
                continue
    
    # 如果依然是 0，則啟動核心備援
    if len(tickers) < 5:
        st.warning("⚠️ 證交所連線遭封鎖，已啟動【核心戰略名單】模式。")
        for tid, name in core_backup.items():
            tickers.append(f"{tid}.TW")
            names_map[tid] = name
            
    return tickers, names_map

# ============================================
# 2. 核心分析邏輯 (保持穩定)
# ============================================
def master_sniper_logic(df, tid, name, vol_gate, trail_p):
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v
    close = df['Close']
    dif = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff().iloc[-1]
    is_break = close.iloc[-1] > df['High'].rolling(20).max().shift(1).iloc[-1]
    score = 40 + (25 if dif > 0 else -10) + (20 if is_break else 0) + (10 if v_ratio > 1.2 else 0)
    last_p = round(float(close.iloc[-1]), 2)
    return {
        "名稱": name, "代號": tid, "綜合勝率": int(min(98, score)),
        "氣勢分析": "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行",
        "能量分析": "⛽ 油箱爆滿" if v_ratio > 1.5 else "🚗 油量正常",
        "明日進場區": f"{round(last_p * 0.98, 2)} ~ {round(last_p * 0.995, 2)}",
        "防守價": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. 執行介面
# ============================================
st.title("🏹 2026 全景獵殺系統 v15.0 - 名單防禦版")

min_gate = st.sidebar.slider("🎯 勝率門檻", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落", 3.0, 15.0, 7.0)

if st.button("🔴 啟動 1/1800+ 全地毯獵殺", type="primary"):
    final_results = []
    with st.status("📡 偵測雷達掃描中...", expanded=True) as status:
        tickers, names_map = get_1800_market_list_armored()
        st.write(f"✅ 成功鎖定 {len(tickers)} 支標的，開始掃描...")
        
        progress_bar = st.progress(0)
        chunk_size = 35 # 調整批次大小，防止被 Yahoo 封鎖
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=20)
                for t in chunk:
                    tid = t.split(".")[0]
                    df = data[t] if len(chunk) > 1 else data
                    res = master_sniper_logic(df, tid, names_map.get(tid, tid), vol_limit, trail_pct)
                    if res and res['綜合勝率'] >= min_gate:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺完成！", state="complete", expanded=False)

    if final_results:
        st.success(f"📊 報告：篩選出 {len(final_results)} 支符合標的。")
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        df_final['綜合勝率'] = df_final['綜合勝率'].apply(lambda x: f"{x}%")
        st.dataframe(df_final, use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ 掃描完畢，無人符合標。請調低門檻。")
