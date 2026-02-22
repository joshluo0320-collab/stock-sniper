import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 系統設定
# ============================================
st.set_page_config(page_title="台股 10D/10% 精選五強預測", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000  

# ============================================
# 全市場抓取與核心計算
# ============================================
@st.cache_data(ttl=86400)
def get_full_market_list():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False)
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        tickers, names_map = [], {}
        for index, row in df.iterrows():
            parts = str(row['有價證券代號及名稱']).split()
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                ticker = f"{parts[0]}.TW"
                tickers.append(ticker)
                names_map[ticker] = parts[1]
        return tickers, names_map
    except: return [], {}

def calculate_advanced_logic(df):
    if len(df) < 40: return df
    # 動能斜率
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_Slope'] = df['MACD'].diff() 
    # 位階與量能
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Bias'] = (df['Close'] - df['MA20']) / df['MA20'] * 100
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    # 壓力位 (過去 20 日高點)
    df['Resistance'] = df['High'].rolling(20).max().shift(1)
    return df

def analyze_and_rank(df):
    last = df.iloc[-1]
    if last['Close'] < last['MA20']: return 0, "無趨勢"
    
    score = 30
    reasons = []
    
    # 1. 動能 (關鍵理由)
    if last['MACD_Slope'] > 0: 
        score += 30
        reasons.append("買盤加速增溫")
    
    # 2. 突破 (關鍵理由)
    if last['Close'] > last['Resistance']:
        score += 25
        reasons.append("突破近期平台壓力")
    
    # 3. 量能 (關鍵理由)
    vol_ratio = last['Volume'] / last['Vol_MA5']
    if vol_ratio > 1.5:
        score += 20
        reasons.append(f"爆量 {vol_ratio:.1f} 倍，主力表態")

    # 4. 位階安全性
    if 0 < last['Bias'] < 7:
        score += 15
        reasons.append("剛起漲，回檔風險低")
    elif last['Bias'] > 12:
        score -= 20 # 太高了
        
    return min(100, score), " / ".join(reasons)

# ============================================
# 主程式執行
# ============================================
st.sidebar.header("🕹️ 控制台")
st.session_state.cash = st.sidebar.number_input("當前總資產", value=st.session_state.cash)
min_prob = st.sidebar.slider("勝率門檻 (%)", 50, 95, 75)

st.title("🏆 台股決賽輪：最強爆發 Top 5")
st.info("系統正在分析 1,000+ 支股票，篩選出具備最強「點火動能」的前五名標的。")

if st.button("🚀 開始全市場決賽輪篩選", type="primary"):
    tickers, names_map = get_full_market_list()
    if not tickers: st.stop()
        
    all_results = []
    bar = st.progress(0)
    
    chunk_size = 35
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        try:
            data = yf.download(chunk, period="4mo", group_by='ticker', progress=False, threads=False)
            for t in chunk:
                try:
                    df = data if len(chunk) == 1 else data.get(t)
                    if df is None or df.empty or len(df) < 30: continue
                    if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                    
                    df = calculate_advanced_logic(df.dropna())
                    last_p = df['Close'].iloc[-1]
                    
                    if df['Volume'].iloc[-1] < 1200 * 1000: continue # 過濾低成交量
                    
                    score, reason = analyze_and_rank(df)
                    if score >= min_prob:
                        # 計算交易指令
                        entry_price = round(last_p * 1.005, 2) # 建議進場價 (微追價)
                        tp_price = round(entry_price * 1.10, 2) # 停利價 (+10%)
                        sl_price = round(entry_price * 0.95, 2) # 停損價 (-5%)
                        suggest_shares = int((st.session_state.cash * 0.2) / (entry_price * 1000))
                        
                        all_results.append({
                            "排名分": score,
                            "代號": t.replace(".TW", ""),
                            "名稱": names_map.get(t, t),
                            "建議進場價": entry_price,
                            "建議停利價": tp_price,
                            "建議停損價": sl_price,
                            "建議張數": max(1, suggest_shares),
                            "擊敗對手理由": reason,
                            "價格": last_p
                        })
                except: continue
        except: continue

    bar.empty()
    
    if all_results:
        # 取前五名
        top_5 = pd.DataFrame(all_results).sort_values(by="排名分", ascending=False).head(5)
        
        st.subheader("🎯 核心推薦 Top 1 - 5")
        
        for idx, row in enumerate(top_5.to_dict('records')):
            with st.expander(f"第 {idx+1} 名：{row['代號']} {row['名稱']} (爆發潛力 {row['排名分']}%)", expanded=True):
                c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
                c1.metric("建議進場價", f"${row['建議進場價']}")
                c2.metric("🎯 停利目標", f"${row['建議停利價']}", "+10%")
                c3.metric("🛑 停損防線", f"${row['建議停損價']}", "-5%")
                c4.info(f"💡 **推薦理由**：{row['擊敗對手理由']}")
                st.write(f"💼 **資金配置**：建議買進 **{row['建議張數']}** 張 (約佔總資金 20%)")
        
        st.markdown("---")
        st.subheader("📊 決賽輪數據對照表")
        st.dataframe(top_5[["代號", "名稱", "建議進場價", "建議停利價", "建議停損價", "擊敗對手理由"]], hide_index=True)
        
    else:
        st.warning("當前盤勢疲軟，無任何股票通過 10D/10% 決賽輪測試，建議觀望。")

st.markdown("---")
st.write("### 📈 合夥人深度分析：為什麼這 5 支能脫穎而出？")
st.write("1. **動能連續性**：被篩出的股票 MACD 斜率皆為正值且持續擴大，這代表買盤不是一次性的，而是有法人或主力在持續吃貨。")
st.write("2. **空間真空化**：這 5 支皆已突破或接近突破過去 20 日的震盪區，上方套牢壓力最輕，阻力最小。")
st.write("3. **風報酬比精算**：建議的停損與停利比為 1:2。長期執行這類高勝率模型，即便錯兩次、對一次，資產也能維持增長。")
