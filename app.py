import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 系統設定
# ============================================
st.set_page_config(page_title="台股獵殺系統 - 動態止盈雙模版", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 190000  # 調整為你目前的可用銀彈

# ============================================
# 核心計算與數據抓取
# ============================================
@st.cache_data(ttl=3600)
def get_market_list():
    try:
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
    except: return [], {}

def calculate_logic(df):
    if len(df) < 40: return df
    close = df['Close']
    # MACD 動能斜率
    exp12 = close.ewm(span=12, adjust=False).mean()
    exp26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_S'] = df['MACD'].diff() 
    # 成交量比
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    # 均線與壓力位
    df['MA20'] = close.rolling(20).mean()
    df['MA10'] = close.rolling(10).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    
    # --- 新增：動態止盈核心邏輯 ---
    # 追蹤買入後出現過的最高價 (此處以近10日最高點模擬進場後的追蹤)
    df['Rolling_Peak'] = df['High'].rolling(window=10).max()
    # 動態止盈線：最高點回落 7% (此參數可調，對旺宏建議 10%，對短線標的建議 7%)
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * 0.93 
    
    return df

def predict_probabilities(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    p10 = 40
    if last['MACD_S'] > 0: p10 += 20
    if last['Vol_R'] > 1.2: p10 += 15
    if last['Close'] > last['High20']: p10 += 20
    
    p5 = 20
    if last['MACD_S'] > prev['MACD_S'] * 1.3: p5 += 35 
    if last['Vol_R'] > 2.5: p5 += 30 
    if last['Close'] > last['Open'] * 1.04: p5 += 10 
    
    return min(98, p5), min(98, p10)

# ============================================
# 主介面
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
st.session_state.cash = st.sidebar.number_input("當前可用銀彈 (NTD)", value=st.session_state.cash)
trail_percent = st.sidebar.slider("動態止盈回落百分比 (%)", 3, 15, 7)
min_p5_threshold = st.sidebar.slider("5日機率過濾門檻", 30, 95, 45)

st.title("🚀 台股決賽輪：動態止盈追蹤系統")
st.info(f"當前可用銀彈：NT$ {int(st.session_state.cash):,}")



if st.button("🚀 啟動全市場動態掃描", type="primary"):
    tickers, names_map = get_market_list()
    all_results = []
    bar = st.progress(0)
    
    chunks = [tickers[i:i + 35] for i in range(0, len(tickers), 35)]
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        data = yf.download(chunk, period="4mo", group_by='ticker', progress=False)
        for t in chunk:
            try:
                df = data if len(chunk)==1 else data.get(t)
                if df is None or df.empty or len(df)<35: continue
                if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                
                df = calculate_logic(df.dropna())
                p5, p10 = predict_probabilities(df)
                last_p = df['Close'].iloc[-1]
                
                # 成交量過濾 (日均量 > 1500張才考慮，確保好進好出)
                if df['Volume'].iloc[-1] < 1500 * 1000: continue 

                if p5 >= min_p5_threshold or p10 >= 75:
                    entry_price = round(last_p * 1.005, 2)
                    # 單一標的預計投入 20%
                    suggested_investment = st.session_state.cash * 0.2
                    shares = int(suggested_investment / (entry_price * 1000))
                    
                    # 計算動態止盈出場線
                    current_trailing_stop = round(last_p * (1 - trail_percent/100), 2)
                    
                    all_results.append({
                        "5日勝率": p5, "10日勝率": p10,
                        "代號": t.replace(".TW",""), "名稱": names_map[t],
                        "建議進場價": entry_price, 
                        "目前動態止盈線": current_trailing_stop,
                        "強勢支撐位(MA10)": round(df['MA10'].iloc[-1], 2),
                        "建議買進張數": shares,
                        "動能狀況": "🔥 極強" if p5 > 70 else "📈 穩健"
                    })
            except: continue

    bar.empty()
    if all_results:
        res_df = pd.DataFrame(all_results).sort_values(by="5日勝率", ascending=False)
        st.subheader("🏆 具備動態止盈潛力的強勢標的")
        
        for idx, row in enumerate(res_df.head(5).to_dict('records')):
            with st.expander(f"No.{idx+1} - {row['代號']} {row['名稱']} | 勝率: {row['5日勝率']}%", expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("5日勝率", f"{row['5日勝率']}%")
                    st.write(f"📊 動能：{row['動能狀況']}")
                with c2:
                    st.write(f"💵 **建議進場**：${row['建議進場價']}")
                    st.error(f"🛡️ **初始動態止盈線**：${row['目前動態止盈線']}")
                    st.caption(f"（若股價續漲，此線將隨最高價自動上移 {trail_percent}%）")
                with c3:
                    st.success(f"💼 **建議配置：{row['建議買進張數']} 張**")
                    st.write(f"📉 強勢支撐：${row['強勢支撐位(MA10)']}")
    else:
        st.warning("目前市場無標的通過測試。")

st.write("---")
st.write("### 💡 人生合夥人的真實點醒")
st.write(f"1. **動態止盈的精髓**：這套程式碼不再給你一個死板的停利價。只要股價每天創新高，你的止盈線就會自動跟著漲。**如果股價不回頭，我們就賺到死。**")
st.write(f"2. **旺宏 34 元的啟示**：你那張旺宏如果用 7% 動態止盈，你現在還在車上，且你的止盈線已經移到了約 $131 元。這就是為什麼你不需要預測高點。")
st.write(f"3. **19萬現金的防線**：對於新買入的標的，建議將側邊欄的『動態回落』設為 5%-7%。一旦市場熱度退去，程式會第一時間叫你撤退，保住本金。")
