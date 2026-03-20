import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用不安全請求警告 (避免在 Streamlit Cloud 噴警告)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統與 UI 設定
# ============================================
st.set_page_config(page_title="台股決賽輪 - 專業修復版", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
min_p10_threshold = st.sidebar.slider("📈 10日趨勢門檻 (%)", 5, 95, 40)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)
# 🛡️ 流動性門檻：建議設 500，排除無量殭屍股
min_vol_lots = st.sidebar.slider("🌊 流動性門檻 (5日均張)", 0, 3000, 500)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存設定")
inventory_input = st.sidebar.text_area("格式: 代號,成本", value="2337,34\n1409,16.5")

# ============================================
# 2. 核心運算與過濾邏輯 (修復 ValueError)
# ============================================
def calculate_logic(df, tp_pct, min_vol):
    """計算技術指標並執行流動性過濾"""
    if df.empty or len(df) < 20: 
        return None
        
    # 處理 yfinance 可能產生的 MultiIndex 欄位
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df.dropna()
    
    # 🌊 流動性過濾：取得最新的 5 日平均成交量 (張)
    # 修正點：使用 .iloc[-1] 確保進行單一數值比較
    avg_vol_series = df['Volume'].rolling(5).mean() / 1000
    current_avg_vol = avg_vol_series.iloc[-1]
    
    if current_avg_vol < min_vol:
        return None

    close = df['Close']
    # 10D 趨勢指標：MACD 斜率
    df['MACD_S'] = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff() 
    # 5D 噴發指標：成交量比率
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    # 壓力位：20日高點
    df['High20'] = df['High'].rolling(20).max().shift(1)
    # 動態止盈：歷史最高點回落
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    
    return df

@st.cache_data(ttl=3600)
def get_full_market_list():
    """爬取上市與上櫃完整代號"""
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    tickers, names = [], {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, verify=False, timeout=10)
            res.encoding = 'big5'
            soup = BeautifulSoup(res.text, 'lxml')
            for row in soup.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) > 0:
                    text = cols[0].text.strip().split()
                    if len(text) >= 2 and len(text[0]) == 4 and text[0].isdigit():
                        # 上市用 .TW, 上櫃用 .TWO
                        suffix = ".TW" if "strMode=2" in url else ".TWO"
                        t = f"{text[0]}{suffix}"
                        tickers.append(t)
                        names[t] = text[1]
        except:
            continue
    
    # 備援清單：若網頁爬取失敗，確保至少有基本標的
    if not tickers:
        backup = ["2330.TW", "2337.TW", "1409.TW", "3234.TW", "2454.TW"]
        return backup, {t: "備援標的" for t in backup}
        
    return tickers, names

# ============================================
# 3. 畫面顯示邏輯
# ============================================
st.title("🛡️ 台股決賽輪：全市場掃描與庫存監控")

# --- 第一區塊：庫存監控 (不套用流動性過濾) ---
st.subheader("💰 我的庫存盈虧與動態撤退線")
if st.button("📊 重新整理庫存報告"):
    inv_results = []
    items = [line.split(',') for line in inventory_input.split('\n') if ',' in line]
    
    for tid, cost in items:
        tid = tid.strip()
        # 嘗試上市或上櫃代號
        df_inv = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df_inv.empty:
            df_inv = yf.download(f"{tid}.TWO", period="1y", progress=False)
            
        if not df_inv.empty:
            # 庫存區 min_vol 設為 0，確保不管量多小都會顯示
            df_proc = calculate_logic(df_inv, trail_percent, 0)
            if df_proc is not None:
                last_p = float(df_proc['Close'].iloc[-1])
                stop_p = float(df_proc['Trailing_Stop_Line'].iloc[-1])
                profit = (last_p / float(cost) - 1) * 100
                inv_results.append({
                    "代號": tid, "成本": float(cost), "現價": round(last_p, 2),
                    "累計損益": f"{round(profit, 2)}%",
                    "動態止盈線": round(stop_p, 2),
                    "狀態": "⚠️ 建議撤退" if last_p < stop_p else "✅ 穩健持有"
                })
    if inv_results:
        st.table(pd.DataFrame(inv_results))
    else:
        st.warning("查無庫存資料，請檢查代號輸入是否正確。")

st.markdown("---")

# --- 第二區塊：全市場掃描 ---
st.subheader(f"🔍 全市場趨勢標的篩選 (門檻: {min_p10_threshold}%)")
if st.button("🔴 啟動全市場獵殺掃描", type="primary"):
    all_tickers, names_map = get_full_market_list()
    st.info(f"掃描池規模：{len(all_tickers)} 支標的。排除 5 日均張低於 {min_vol_lots} 張之股票。")
    
    scan_results = []
    bar = st.progress(0)
    
    # 為了穩定性，採用分組下載
    chunk_size = 50
    chunks = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        try:
            data = yf.download(chunk, period="4mo", group_by='ticker', progress=False, timeout=10)
            for t in chunk:
                df = data[t] if len(chunk) > 1 else data
                if df is None or df.empty: continue
                
                df_p = calculate_logic(df.dropna(), trail_percent, min_vol_lots)
                if df_p is not None:
                    last = df_p.iloc[-1]
                    # 趨勢評分邏輯
                    p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (20 if last['Close'] > last['High20'] else 0)
                    
                    if p10 >= min_p10_threshold:
                        scan_results.append({
                            "代號": t.split(".")[0],
                            "名稱": names_map.get(t, "未知"),
                            "趨勢強度": f"{int(p10)}%",
                            "現價": round(float(last['Close']), 2),
                            "5日均張": int(df['Volume'].rolling(5).mean().iloc[-1] / 1000),
                            "動態止盈線": round(float(last['Trailing_Stop_Line']), 2)
                        })
        except:
            continue
            
    bar.empty()
    if scan_results:
        st.dataframe(pd.DataFrame(scan_results).sort_values(by="趨勢強度", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning("當前盤勢下，無符合流動性與趨勢門檻之標的。")
