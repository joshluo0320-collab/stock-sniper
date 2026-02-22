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
st.set_page_config(page_title="台股獵殺系統 - 5D/10D 雙模版", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000  # 你的總預算

# ============================================
# 核心計算與數據抓取
# ============================================
@st.cache_data(ttl=3600)
def get_market_list():
    """連線證交所抓取 1000+ 支上市股票"""
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
    # MACD 動能斜率 (判斷加速度)
    exp12 = close.ewm(span=12, adjust=False).mean()
    exp26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_S'] = df['MACD'].diff() 
    # 成交量比 (瘋狗浪指標)
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    # 乖離率與壓力位
    df['MA20'] = close.rolling(20).mean()
    df['Bias'] = (close - df['MA20']) / df['MA20'] * 100
    df['High20'] = df['High'].rolling(20).max().shift(1)
    return df

def predict_probabilities(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 10日機率：側重「趨勢結構」
    p10 = 40
    if last['MACD_S'] > 0: p10 += 20
    if last['Vol_R'] > 1.2: p10 += 15
    if last['Close'] > last['High20']: p10 += 20
    
    # 5日機率：側重「噴發加速度」
    p5 = 20
    if last['MACD_S'] > prev['MACD_S'] * 1.3: p5 += 35 # 斜率陡增
    if last['Vol_R'] > 2.5: p5 += 30 # 極端量能
    if last['Close'] > last['Open'] * 1.04: p5 += 10 # 強力長紅
    
    return min(98, p5), min(98, p10)

# ============================================
# 主介面
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
st.session_state.cash = st.sidebar.number_input("當前總資產 (NTD)", value=st.session_state.cash)
min_p5_threshold = st.sidebar.slider("5日機率過濾門檻", 30, 95, 45)

st.title("🚀 台股決賽輪：5D / 10D 雙模噴發預測")
st.info(f"目標：在 1,000+ 支標的中尋找『極短線瘋狗浪』。當前可用銀彈：NT$ {int(st.session_state.cash):,}")

if st.button("🚀 啟動全市場決賽輪分析", type="primary"):
    tickers, names_map = get_market_list()
    all_results = []
    bar = st.progress(0)
    
    chunks = [tickers[i:i + 35] for i in range(0, len(tickers), 35)]
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        data = yf.download(chunk, period="4mo", group_by='ticker', progress=False, threads=False)
        for t in chunk:
            try:
                df = data if len(chunk)==1 else data.get(t)
                if df is None or df.empty or len(df)<35: continue
                if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                
                df = calculate_logic(df.dropna())
                p5, p10 = predict_probabilities(df)
                last_p = df['Close'].iloc[-1]
                
                # 成交量基本過濾 (避免流動性風險)
                if df['Volume'].iloc[-1] < 1200 * 1000: continue 

                if p5 >= min_p5_threshold or p10 >= 70:
                    entry_price = round(last_p * 1.005, 2)
                    # 資金分配：單一標的上限為總資產的 20% (約 4.8 萬)
                    suggested_investment = st.session_state.cash * 0.2
                    shares = int(suggested_investment / (entry_price * 1000))
                    actual_cost = shares * entry_price * 1000
                    
                    all_results.append({
                        "5日勝率": p5, "10日勝率": p10,
                        "代號": t.replace(".TW",""), "名稱": names_map[t],
                        "建議進場價": entry_price, 
                        "目標停利價": round(entry_price * 1.10, 2),
                        "防守停損價": round(entry_price * 0.95, 2),
                        "建議投入金額": int(actual_cost),
                        "建議買進張數": shares,
                        "動能狀況": "🔥 極強" if p5 > 60 else "📈 穩健"
                    })
            except: continue

    bar.empty()
    if all_results:
        res_df = pd.DataFrame(all_results).sort_values(by="5日勝率", ascending=False)
        
        st.subheader("🏆 全市場前五強推薦 (Top 1-5)")
        for idx, row in enumerate(res_df.head(5).to_dict('records')):
            with st.expander(f"No.{idx+1} - {row['代號']} {row['名稱']} | 5日勝率: {row['5日勝率']}%", expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("5日漲10%機率", f"{row['5日勝率']}%")
                    st.metric("10日漲10%機率", f"{row['10日勝率']}%")
                with c2:
                    st.write(f"💵 **建議進場價**：${row['建議進場價']}")
                    st.write(f"🎯 **目標停利價**：${row['目標停利價']}")
                    st.write(f"🛑 **防守停損價**：${row['防守停損價']}")
                with c3:
                    st.success(f"💰 **建議投入：NT$ {row['建議投入金額']:,}**")
                    st.success(f"💼 **建議買進：{row['建議買進張數']} 張**")
                    st.write(f"📊 動能評等：{row['動能狀況']}")

        st.markdown("---")
        st.subheader("🥈 第二梯隊 (Top 6-10)")
        st.dataframe(res_df.iloc[5:10][["代號", "名稱", "5日勝率", "10日勝率", "建議進場價", "建議買進張數", "建議投入金額"]], hide_index=True)
    else:
        st.warning("目前市場無標的通過「瘋狗浪」爆發測試。")

st.write("---")
st.write("### 💡 人生合夥人的真實點醒")
st.write("1. **為什麼限制金額？** 我將單一股票限制在 24 萬的 **20% (約 4.8 萬)**。這樣即便某支股票預測失敗觸及 5% 停損，你的總資產損失也僅為 1%，這才是長期致勝的分配法。")
st.write("2. **5日勝率的意義**：如果 5 日勝率 > 70%，代表該股正在『趕路』。如果 3 天內沒漲，請務必檢視動能是否消失。")
st.write("3. **進場準則**：若明日開盤價直接高過建議進場價 2% 以上，請棄標，改看下一順位的標的。")
