import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import urllib3

# 關閉連線警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 系統設定
# ============================================
st.set_page_config(page_title="台股右側爆發 - 精選排序版", layout="wide")

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
        # 抓取上市股票清單
        dfs = pd.read_html(res.text)
        df = dfs[0]
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
    # 推進力 (MACD)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_Slope'] = df['MACD'].diff() 
    # 乖離率 (判斷位階)
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Bias'] = (df['Close'] - df['MA20']) / df['MA20'] * 100
    # 成交量趨勢
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    return df

def analyze_right_side(df):
    last = df.iloc[-1]
    prob = 30
    
    # 強勢股必備條件：站上月線
    if last['Close'] < last['MA20']: return 0, "趨勢向下"
    
    # 評分邏輯 (10D/10% 預測)
    if last['MACD_Slope'] > 0: prob += 25  # 動能轉強
    if last['Volume'] > last['Vol_MA5'] * 1.5: prob += 20 # 帶量進場
    if last['Close'] > df['High'].rolling(20).max().iloc[-2]: prob += 20 # 創新高
    if 0 < last['Bias'] < 8: prob += 15 # 剛起漲 (位階健康)
    
    # 扣分：過熱警示
    if last['Bias'] > 15: prob -= 20 # 漲太兇，容易回撤
    
    return min(98, prob), "符合順勢條件"

# ============================================
# 主程式執行
# ============================================
st.sidebar.header("🕹️ 右側交易控制台")
st.session_state.cash = st.sidebar.number_input("當前總資產 (計算比例用)", value=st.session_state.cash)

price_limit = st.sidebar.slider("股價預算", 10, 300, (20, 160))
min_prob_threshold = st.sidebar.slider("爆發勝率門檻 (%)", 50, 95, 75)

st.title("🚀 右側順勢 - 10D/10% 決賽輪預測")
st.markdown("針對全台股 **1,000+** 標的執行「爆發力點火測試」，篩選最精確的 **Top 1-3**。")

if st.button("🔥 開始精確篩選", type="primary"):
    tickers, names_map = get_full_market_list()
    if not tickers: 
        st.error("無法連線證交所。")
        st.stop()
        
    raw_results = []
    bar = st.progress(0)
    
    chunk_size = 30
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        try:
            # 批次下載數據
            data = yf.download(chunk, period="4mo", group_by='ticker', progress=False, threads=False)
            for t in chunk:
                try:
                    df = data if len(chunk) == 1 else data.get(t)
                    if df is None or df.empty or len(df) < 30: continue
                    if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                    
                    df = calculate_advanced_logic(df.dropna())
                    last_p = df['Close'].iloc[-1]
                    
                    # 篩選條件
                    if not (price_limit[0] <= last_p <= price_limit[1]): continue
                    if df['Volume'].iloc[-1] < 1000 * 1000: continue # 至少千張成交
                    
                    prob, status = analyze_right_side(df)
                    
                    if prob >= min_prob_threshold:
                        # 建議進場金額：單一標的不超過總資產的 25%
                        suggest_shares = int((st.session_state.cash * 0.25) / (last_p * 1000))
                        raw_results.append({
                            "代號": t.replace(".TW", ""),
                            "名稱": names_map.get(t, t),
                            "預測勝率": prob,
                            "價格": last_p,
                            "建議進場(張)": max(1, suggest_shares),
                            "動能指標": "🚀 強勁加速" if df['MACD_Slope'].iloc[-1] > 0 else "🐢 增速趨緩",
                            "成交量比": f"{df['Volume'].iloc[-1]/df['Vol_MA5'].iloc[-1]:.1f}倍"
                        })
                except: continue
        except: continue

    bar.empty()
    
    if raw_results:
        # 進行排序
        df_final = pd.DataFrame(raw_results).sort_values(by=["預測勝率", "價格"], ascending=[False, True])
        
        st.subheader("🏆 本日精選 Top 3 (精確推薦)")
        top_3 = df_final.head(3)
        cols = st.columns(3)
        for idx, row in enumerate(top_3.to_dict('records')):
            with cols[idx]:
                st.info(f"排名 {idx+1}：{row['代號']} {row['名稱']}")
                st.metric("爆發機率", f"{row['預測勝率']}%")
                st.success(f"💰 建議買進：{row['建議進場(張)']} 張")
                st.write(f"📊 動能：{row['動能指標']}")
                st.write(f"🔋 量能：{row['成交量比']}")
        
        st.markdown("---")
        st.subheader("📋 其他潛力標的 (候補名單)")
        st.dataframe(df_final.iloc[3:], use_container_width=True, hide_index=True)
    else:
        st.warning("目前市場無符合「右側高勝率」之標的，建議空手觀望。")

# ============================================
# 底部說明 (直白版)
# ============================================
st.markdown("---")
st.write("### 💡 合夥人提醒")
st.write("1. **排序規則**：Top 1 是考量了「動能斜率」與「位階安全度」後的最優解。")
st.write("2. **資金分配**：建議將 24 萬銀彈分散在 Top 1-3 標的中，降低單點風險。")
st.write("3. **停損意識**：右側交易若跌破 5 日線或 20 日線，爆發基因即消失，應果斷撤出。")

# 圖表示例
