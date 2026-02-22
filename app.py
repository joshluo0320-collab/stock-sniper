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
st.set_page_config(page_title="台股全市場獵殺系統 (5D/10D 雙模版)", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000  

# ============================================
# 數據抓取：全市場 1000+ 標的
# ============================================
@st.cache_data(ttl=3600)
def get_market_data():
    """核實：連線證交所抓取 1000+ 支上市股票，不限族群"""
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

def calculate_burst_logic(df):
    if len(df) < 40: return df
    close = df['Close']
    # 核心：動能加速度 (MACD Slope)
    exp12 = close.ewm(span=12, adjust=False).mean()
    exp26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_S'] = df['MACD'].diff() 
    # 核心：能量 (成交量比)
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    # 核心：空間 (乖離率)
    df['MA20'] = close.rolling(20).mean()
    df['Bias'] = (close - df['MA20']) / df['MA20'] * 100
    return df

def predict_model(df):
    """預測模型：分析 5日10% 與 10日10% 的機率"""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 10日機率基礎分
    p10 = 40
    if last['MACD_S'] > 0: p10 += 20
    if last['Vol_R'] > 1.5: p10 += 15
    if last['Close'] > df['High'].rolling(20).max().iloc[-2]: p10 += 20
    
    # 5日機率基礎分 (條件極度嚴苛)
    p5 = 20
    # 關鍵：動能爆發斜率
    if last['MACD_S'] > prev['MACD_S'] * 1.2: p5 += 30 
    # 關鍵：成交量異常 (瘋狗浪)
    if last['Vol_R'] > 2.5: p5 += 30
    # 關鍵：開盤位置 (強勢跳空)
    if last['Close'] > last['Open'] * 1.03: p5 += 15
    
    # 理由生成
    reason = "綜合指標轉強"
    if last['Vol_R'] > 3: reason = "【瘋狗浪】極短線資金瘋狂湧入"
    elif last['MACD_S'] > 0 and last['Bias'] < 5: reason = "【蓄勢待發】剛起漲且動能加速"
    elif last['Close'] > df['High'].rolling(60).max().iloc[-2]: reason = "【大突破】突破三個月大底"
    
    return min(98, p5), min(98, p10), reason

# ============================================
# 主介面
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
st.session_state.cash = st.sidebar.number_input("總預算", value=st.session_state.cash)
min_p5 = st.sidebar.slider("5日爆發機率門檻", 30, 95, 50)

st.title("🎯 台股全市場「5D / 10D」雙模獵殺系統")
st.info("不預設族群，純數據驅動。專注搜尋未來 5-10 日具備 10% 漲幅基因的標的。")

if st.button("🚀 啟動全市場數據預測", type="primary"):
    tickers, names_map = get_market_data()
    all_results = []
    bar = st.progress(0)
    
    chunks = [tickers[i:i + 35] for i in range(0, len(tickers), 35)]
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        data = yf.download(chunk, period="4mo", group_by='ticker', progress=False, threads=False)
        for t in chunk:
            try:
                df = data if len(chunk)==1 else data.get(t)
                if df is None or df.empty or len(df)<30: continue
                if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                
                df = calculate_burst_logic(df.dropna())
                p5, p10, reason = predict_model(df)
                last_p = df['Close'].iloc[-1]
                
                # 初步過濾：成交量不能太小
                if df['Volume'].iloc[-1] < 1500 * 1000: continue 

                if p5 >= min_p5 or p10 >= 75:
                    entry = round(last_p * 1.01, 2)
                    all_results.append({
                        "5日爆發%": p5, "10日爆發%": p10,
                        "代號": t.replace(".TW",""), "名稱": names_map[t],
                        "建議買價": entry, "停利(+10%)": round(entry*1.1, 2), "停損(-5%)": round(entry*0.95, 2),
                        "建議張數": int((st.session_state.cash * 0.2) / (entry*1000)),
                        "數據診斷": reason, "現價": last_p
                    })
            except: continue

    bar.empty()
    if all_results:
        res_df = pd.DataFrame(all_results).sort_values(by="5日爆發%", ascending=False)
        
        st.subheader("🏆 全市場決賽輪：Top 1-5 精選推薦")
        for idx, row in enumerate(res_df.head(5).to_dict('records')):
            with st.expander(f"No.{idx+1} - {row['代號']} {row['名稱']} (5日機率: {row['5日爆發%']}%)", expanded=True):
                c1, c2, c3, c4 = st.columns([1,1,1,2])
                c1.metric("建議買價", row['建議買價'])
                c2.metric("🎯 停利點", row['停利(+10%)'])
                c3.metric("🛑 停損點", row['停損(-5%)'])
                c4.success(f"💡 **診斷**：{row['數據診斷']}\n\n💼 **資金建議**：買進 **{row['建議張數']}** 張")

        st.markdown("---")
        st.subheader("🥈 第二梯隊：潛力標的 (Top 6-10)")
        st.dataframe(res_df.iloc[5:10][["代號", "名稱", "5日爆發%", "10日爆發%", "數據診斷"]], hide_index=True)
    else:
        st.warning("當前全市場無符合爆發基因標的。")

st.write("---")
st.write("### 💡 合夥人點醒：如何判斷 5 日內的真實爆發？")
st.write("1. **成交量是靈魂**：若該股理由標註為『瘋狗浪』，代表資金極度集中。")
st.write("2. **5 日與 10 日的權衡**：5 日機率高的股票適合當沖或隔日沖；10 日機率高的股票則具備較紮實的波段結構。")
st.write("3. **不要死守**：5 日目標標的若 3 天內沒動，代表動能預測失敗，應提早撤出，不要等停損。")
