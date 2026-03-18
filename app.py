import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import urllib3

# 禁用警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統與 UI 設定
# ============================================
st.set_page_config(page_title="台股決賽輪 - 穩定修正版", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
# 門檻建議先設 30%，確保能看到數據流
min_p10_threshold = st.sidebar.slider("📈 10日趨勢過濾門檻", 10, 95, 30)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

# ============================================
# 2. 核心數據模組 (修復 ImportError)
# ============================================
@st.cache_data(ttl=3600)
def get_market_list():
    """抓取全市場上市標的 - 修正解析器問題"""
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        # 增加 Headers 模擬瀏覽器，防止被封鎖
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, verify=False)
        
        # 強制指定 flavor='lxml' 避免 ImportError
        df_list = pd.read_html(res.text, flavor='lxml')
        df = df_list[0]
        
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        tickers, names = [], {}
        for _, row in df.iterrows():
            parts = str(row['有價證券代號及名稱']).split()
            # 嚴格篩選：代號 4 碼且為數字的才是普通股
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                t = f"{parts[0]}.TW"
                tickers.append(t)
                names[t] = parts[1]
        return tickers, names
    except Exception as e:
        st.error(f"網頁解析出錯: {e}")
        return [], {}

def calculate_logic(df, tp_pct):
    if len(df) < 25: return df
    close = df['Close']
    # 計算指標
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
    # 10D 趨勢機率
    p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (15 if last['Vol_R'] > 1.1 else 0) + (20 if last['Close'] > last['High20'] else 0)
    # 5D 噴發機率
    p5 = 20 + (40 if last['MACD_S'] > prev['MACD_S'] else 0) + (30 if last['Vol_R'] > 1.5 else 0)
    return min(98, p5), min(98, p10)

# ============================================
# 3. 主介面執行
# ============================================
st.title("🚀 台股全市場 1000+ 穩定掃描系統")

if st.button("🔴 開始掃描所有上市股票", type="primary"):
    tickers, names_map = get_market_list()
    
    if not tickers:
        st.error("無法取得股票清單，請檢查網路或解析套件。")
    else:
        st.write(f"✅ 成功辨識 {len(tickers)} 支上市股票，開始分析...")
        all_results = []
        bar = st.progress(0)
        status = st.empty()

        # 使用 chunk 批次下載 (每組 40 支提高穩定性)
        chunk_size = 40
        chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            bar.progress((i + 1) / len(chunks))
            status.text(f"掃描進度: {i*chunk_size} / {len(tickers)}")
            
            try:
                # 修正 yfinance 的 MultiIndex 報價結構
                data = yf.download(chunk, period="4mo", group_by='ticker', progress=False)
                
                for t in chunk:
                    df = data[t] if len(chunk) > 1 else data
                    if df is None or df.empty or len(df) < 25: continue
                    
                    # 關鍵修正：修復 MultiIndex 欄位取值問題
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    
                    df = calculate_logic(df.dropna(), trail_percent)
                    p5, p10 = predict_probabilities(df)
                    
                    if p10 >= min_p10_threshold:
                        last_p = df['Close'].iloc[-1]
                        all_results.append({
                            "代號": t.replace(".TW",""),
                            "名稱": names_map[t],
                            "10D趨勢": f"{int(p10)}%",
                            "5D噴發": f"{int(p5)}%",
                            "現價": round(float(last_p), 2),
                            "建議進場": round(float(last_p) * 1.005, 2),
                            "動態止盈線": round(df['Trailing_Stop_Line'].iloc[-1], 2)
                        })
            except: continue
        
        bar.empty()
        status.empty()
        
        if all_results:
            st.success(f"完成！共找出 {len(all_results)} 支符合條件標的。")
            st.dataframe(pd.DataFrame(all_results).sort_values(by="10D趨勢", ascending=False), use_container_width=True)
        else:
            st.warning("掃描完畢，但無標的符合門檻。請調低 10D 過濾百分比。")
