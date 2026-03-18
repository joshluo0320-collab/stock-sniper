import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統設定
# ============================================
st.set_page_config(page_title="台股監控 - 鋼鐵穩定版", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
# 門檻調低至 30% 進行壓力測試
min_p10_threshold = st.sidebar.slider("📈 10日趨勢門檻 (%)", 10, 95, 30)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

# ============================================
# 2. 核心數據模組
# ============================================
@st.cache_data(ttl=3600)
def get_market_list():
    """確認：抓取所有上市標的"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    res = requests.get(url, verify=False)
    df = pd.read_html(res.text)[0]
    df.columns = df.iloc[0]
    df = df.iloc[1:]
    tickers, names = [], {}
    for _, row in df.iterrows():
        parts = str(row['有價證券代號及名稱']).split()
        if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
            t = f"{parts[0]}.TW"
            tickers.append(t)
            names[t] = parts[1]
    return tickers, names

def calculate_logic(df, tp_pct):
    close = df['Close']
    # 簡化指標，確保運算不報錯
    exp12 = close.ewm(span=12).mean()
    exp26 = close.ewm(span=26).mean()
    df['MACD_S'] = (exp12 - exp26).diff() 
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    return df

def predict_probabilities(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # 10D 邏輯
    p10 = 40
    if last['MACD_S'] > 0: p10 += 20
    if last['Vol_R'] > 1.1: p10 += 15
    if last['Close'] > last['High20']: p10 += 20
    # 5D 邏輯
    p5 = 20
    if last['MACD_S'] > prev['MACD_S']: p5 += 40
    if last['Vol_R'] > 1.5: p5 += 30
    return min(98, p5), min(98, p10)

# ============================================
# 3. 主介面執行
# ============================================
st.title("🚀 鋼鐵測試：全市場 1000+ 掃描")

if st.button("🔴 開始掃描 (逐一檢查模式)", type="primary"):
    tickers, names_map = get_market_list()
    st.write(f"已抓取 {len(tickers)} 支上市代號，準備下載數據...")
    
    all_results = []
    bar = st.progress(0)
    status_text = st.empty()
    
    # 實測前 200 支 (確保速度並驗證程式正確性)
    test_range = tickers[0:200] 
    
    for i, t in enumerate(test_range):
        bar.progress((i + 1) / len(test_range))
        status_text.text(f"正在掃描: {t} {names_map.get(t, '')}")
        
        try:
            # 逐一抓取，避免批次錯誤
            df = yf.download(t, period="3mo", progress=False)
            if df.empty or len(df) < 20: continue
            
            # 處理多重索引
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df = calculate_logic(df.dropna(), trail_percent)
            p5, p10 = predict_probabilities(df)
            
            # --- 測試：只要大於門檻就顯示 ---
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
        except Exception as e:
            continue
            
    status_text.text("掃描完成！")
    if all_results:
        st.dataframe(pd.DataFrame(all_results), use_container_width=True)
    else:
        st.error("警告：依然無標的符合。請檢查您的網路連線或 yfinance 是否遭封鎖。")
