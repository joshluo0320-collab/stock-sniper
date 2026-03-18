import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統與 UI 設定
# ============================================
st.set_page_config(page_title="台股決賽輪 - 最終穩定版", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
min_p10_threshold = st.sidebar.slider("📈 10日趨勢過濾門檻", 10, 95, 40)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存建倉")
inventory_input = st.sidebar.text_area("代號,成本 (例如: 2337,34)", value="2337,34\n1409,16.5")

# ============================================
# 2. 核心數據模組 (修復讀不到表格問題)
# ============================================
@st.cache_data(ttl=3600)
def get_market_list():
    """使用 BeautifulSoup 強力解析證交所清單"""
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(url, headers=headers, verify=False)
        res.encoding = 'big5' # 證交所使用 big5 編碼
        
        soup = BeautifulSoup(res.text, 'lxml')
        table = soup.find('table', {'class': 'h4'}) # 證交所表格通常帶有此 class
        
        rows = table.find_all('row') if not table else soup.find_all('tr')
        
        tickers, names = [], {}
        for row in rows:
            cols = row.find_all('td')
            if len(cols) > 0:
                text = cols[0].text.strip()
                parts = text.split()
                # 篩選標準：代號 4 碼且為數字 (上市普通股)
                if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                    t = f"{parts[0]}.TW"
                    tickers.append(t)
                    names[t] = parts[1]
        return tickers, names
    except Exception as e:
        st.error(f"解析失敗: {e}")
        return [], {}

def calculate_logic(df, tp_pct):
    if len(df) < 20: return df
    close = df['Close']
    # 技術指標
    exp12 = close.ewm(span=12, adjust=False).mean()
    exp26 = close.ewm(span=26, adjust=False).mean()
    df['MACD_S'] = (exp12 - exp26).diff() 
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    # 動態止盈線
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    return df

def predict_probabilities(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # 10D 趨勢
    p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (15 if last['Vol_R'] > 1.1 else 0) + (20 if last['Close'] > last['High20'] else 0)
    # 5D 噴發
    p5 = 20 + (40 if last['MACD_S'] > prev['MACD_S'] else 0) + (30 if last['Vol_R'] > 1.5 else 0)
    return min(98, p5), min(98, p10)

# ============================================
# 3. 主介面執行
# ============================================
st.title("🚀 台股全市場 1000+ 強力掃描系統")

if st.button("🔴 開始掃描 (修復網頁解析版)", type="primary"):
    tickers, names_map = get_market_list()
    
    if not tickers:
        st.error("清單抓取空值，請確認證交所網站是否維護中。")
    else:
        st.success(f"✅ 已成功辨識 {len(tickers)} 支股票，開始進行瘋狗浪分析...")
        all_results = []
        bar = st.progress(0)
        
        # 批次下載以加速 (每組 40 支)
        chunk_size = 40
        chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            bar.progress((i + 1) / len(chunks))
            try:
                data = yf.download(chunk, period="4mo", group_by='ticker', progress=False, threads=True)
                for t in chunk:
                    df = data[t] if len(chunk) > 1 else data
                    if df is None or df.empty or len(df) < 20: continue
                    
                    # 修復 yf 回傳的 MultiIndex
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    
                    df = calculate_logic(df.dropna(), trail_percent)
                    p5, p10 = predict_probabilities(df)
                    
                    if p10 >= min_p10_threshold:
                        last_p = df['Close'].iloc[-1]
                        all_results.append({
                            "代號": t.replace(".TW",""),
                            "名稱": names_map[t],
                            "10D趨勢分": f"{int(p10)}%",
                            "5D噴發分": f"{int(p5)}%",
                            "現價": round(float(last_p), 2),
                            "建議進場價": round(float(last_p) * 1.005, 2),
                            "動態止盈線": round(df['Trailing_Stop_Line'].iloc[-1], 2)
                        })
            except: continue
            
        bar.empty()
        if all_results:
            st.dataframe(pd.DataFrame(all_results).sort_values(by="10D趨勢分", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.warning("無標的符合門檻。")

st.markdown("---")
# (庫存回測區塊可依此邏輯類推補上)
