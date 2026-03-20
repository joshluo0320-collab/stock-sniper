import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統與 UI 設定
# ============================================
st.set_page_config(page_title="台股全市場獵殺系統 - 專業版", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
min_p10_threshold = st.sidebar.slider("📈 10日趨勢過濾門檻", 10, 95, 40)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)
# 🛡️ 新增：流動性門檻 (單位：張)
min_vol_lots = st.sidebar.slider("🌊 流動性門檻 (5日均張)", 0, 3000, 500)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存建倉")
inventory_input = st.sidebar.text_area("代號,成本", value="2337,34\n1409,16.5")

# ============================================
# 2. 核心數據模組 (含上市、上櫃全抓取)
# ============================================
@st.cache_data(ttl=3600)
def get_full_market_list():
    """抓取上市 (TSE) 與 上櫃 (OTC) 的完整清單"""
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_tickers, names_map = [], {}

    for url in urls:
        try:
            res = requests.get(url, headers=headers, verify=False)
            res.encoding = 'big5'
            soup = BeautifulSoup(res.text, 'lxml')
            rows = soup.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) > 0:
                    text = cols[0].text.strip()
                    parts = text.split()
                    # 篩選代號 4 碼之股票 (不含權證、ETF)
                    if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                        suffix = ".TW" if "strMode=2" in url else ".TWO"
                        t = f"{parts[0]}{suffix}"
                        all_tickers.append(t)
                        names_map[t] = parts[1]
        except Exception as e:
            st.error(f"連線失敗: {url}, 錯誤: {e}")
    return all_tickers, names_map

def calculate_logic(df, tp_pct, min_vol):
    if len(df) < 20: return None
    # 修正 yfinance MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 🛡️ 關鍵新增：流動性過濾 (5日均張低於門檻則淘汰)
    avg_volume_lots = (df['Volume'].rolling(5).mean().iloc[-1]) / 1000
    if avg_volume_lots < min_vol:
        return None

    close = df['Close']
    df['MACD_S'] = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff() 
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    return df

def predict_probabilities(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (15 if last['Vol_R'] > 1.1 else 0) + (20 if last['Close'] > last['High20'] else 0)
    p5 = 20 + (40 if last['MACD_S'] > prev['MACD_S'] else 0) + (30 if last['Vol_R'] > 1.5 else 0)
    return min(98, p5), min(98, p10)

# ============================================
# 3. 主介面執行
# ============================================
st.title("🚀 台股全市場 1800+ 標的獵殺分析")

if st.button("🔴 開始掃描 (含流動性門檻)", type="primary"):
    tickers, names_map = get_full_market_list()
    st.write(f"🔍 已抓取全台股清單：**{len(tickers)} 支標的** (含上市與上櫃)")
    
    all_results = []
    bar = st.progress(0)
    
    # 批次下載
    chunk_size = 50
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        try:
            data = yf.download(chunk, period="4mo", group_by='ticker', progress=False)
            for t in chunk:
                df = data[t] if len(chunk) > 1 else data
                if df is None or df.empty: continue
                
                df = calculate_logic(df.dropna(), trail_percent, min_vol_lots)
                if df is None: continue # 被流動性門檻淘汰
                
                p5, p10 = predict_probabilities(df)
                if p10 >= min_p10_threshold:
                    last_p = df['Close'].iloc[-1]
                    all_results.append({
                        "代號": t.split(".")[0],
                        "名稱": names_map[t],
                        "10D趨勢分": f"{int(p10)}%",
                        "5D噴發分": f"{int(p5)}%",
                        "5日均張": int((df['Volume'].rolling(5).mean().iloc[-1]) / 1000),
                        "現價": round(float(last_p), 2),
                        "動態止盈線": round(df['Trailing_Stop_Line'].iloc[-1], 2)
                    })
        except: continue
    
    bar.empty()
    if all_results:
        st.subheader(f"🏆 符合門檻之標的 (已排除低於 {min_vol_lots} 張之股票)")
        st.dataframe(pd.DataFrame(all_results).sort_values(by="10D趨勢分", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning("無標的符合設定門檻。")
