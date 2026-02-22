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
st.set_page_config(page_title="台股直觀戰情室 (高勝率評分版)", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000  
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {
        '2337.TW': {'cost': 0, 'shares': 1000} 
    }

# ============================================
# 核心功能
# ============================================
@st.cache_data(ttl=86400)
def get_twse_stock_list():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False)
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        if '有價證券別' in df.columns:
            df = df[df['有價證券別'] == '股票']
        
        tickers = []
        names_map = {}
        for index, row in df.iterrows():
            code_name = str(row['有價證券代號及名稱'])
            parts = code_name.split()
            if len(parts) >= 2:
                code = parts[0]
                name = parts[1]
                if len(code) == 4 and code.isdigit():
                    ticker = f"{code}.TW"
                    tickers.append(ticker)
                    names_map[ticker] = name
        return tickers, names_map
    except: return [], {}

def calculate_indicators(df):
    if len(df) < 35: return df
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    return df

# ============================================
# 二次篩選與評分機制
# ============================================
def calculate_ai_score(last_k, vol_ratio, mode):
    """計算這檔股票的爆發力綜合評分 (0-100)"""
    score = 50 # 基礎分
    
    # 1. K線實體強度 (滿分 +20)：判斷主力是否留上影線出貨
    body = abs(last_k['Close'] - last_k['Open'])
    upper_shadow = last_k['High'] - max(last_k['Close'], last_k['Open'])
    if upper_shadow == 0: 
        score += 20
    elif body > 0:
        shadow_ratio = upper_shadow / body
        if shadow_ratio < 0.5: score += 10
        elif shadow_ratio > 2.0: score -= 15 # 上影線太長，扣分
        
    # 2. 量能動能 (滿分 +20)：量增價漲最好
    if vol_ratio >= 2.0: score += 20
    elif vol_ratio >= 1.5: score += 10
    
    # 3. 乖離率控管 (滿分 +10)：避免追高 (僅限右側)
    if mode == 'Right':
        bias = (last_k['Close'] - last_k['MA20']) / last_k['MA20'] * 100
        if 0 < bias <= 8: score += 10 # 剛起漲，最甜
        elif bias > 15: score -= 20 # 漲太多了，危險
        
    return min(100, max(0, int(score)))

def analyze_stock(ticker, stock_name, df, mode, params):
    if df is None or len(df) < 35: return False, None
    
    last = df.iloc[-1]
    price = last['Close']
    
    if last['Volume'] < params['min_volume']: return False, None
    if not (params['price_min'] <= price <= params['price_max']): return False, None

    rsi_val = last['RSI'] if not pd.isna(last['RSI']) else 50
    ma20 = last['MA20']
    
    recent = df.iloc[-10:]
    up_days = sum(recent['Close'] >= recent['Open'])
    win_rate = (up_days / 10) * 100
    vol_ratio = last['Volume'] / last['Vol_MA5'] if last['Vol_MA5'] > 0 else 1.0

    is_match = False
    
    if mode == 'Right':
        if price > ma20 and win_rate >= params['min_win_rate'] and vol_ratio >= params['vol_burst_ratio']: 
            is_match = True
    elif mode == 'Left':
        bias = (price - ma20) / ma20 * 100
        if rsi_val < params['rsi_threshold'] and bias < -params['bias_threshold']: 
            is_match = True

    if is_match:
        # 二次篩選評分
        ai_score = calculate_ai_score(last, vol_ratio, mode)
        
        # 白話文
        if mode == 'Right': comment = "籌碼穩健，剛起漲" if ai_score >= 70 else "有上影線或乖離稍大，需觀察"
        else: comment = "跌深醞釀反彈" if ai_score >= 60 else "空頭排列，僅能搶短"

        return True, {
            "代號": ticker.replace('.TW', ''),
            "名稱": stock_name,
            "AI評分": ai_score, # 用於二次排序
            "現價": price,
            "熱度(RSI)": rsi_val,
            "近期勝率(%)": win_rate, # 已修復 UI 顯示 Bug
            "量能倍數": f"{vol_ratio:.1f}倍",
            "AI 簡評": comment,
            "資金": "✅" if price*1000 <= st.session_state.cash else "❌"
        }
        
    return False, None

# ============================================
# UI 與主程式
# ============================================
st.sidebar.header("🕹️ 操盤控制台")

with st.sidebar.expander("💰 資產狀態", expanded=True):
    st.session_state.cash = st.number_input("可用現金", value=st.session_state.cash, step=1000)
    st.write(f"庫存: 旺宏 {st.session_state.portfolio.get('2337.TW', {}).get('shares', 0)} 股")

st.sidebar.markdown("---")
strategy_mode = st.sidebar.radio("交易策略", ["右側交易 (順勢追漲)", "左側交易 (逆勢抄底)"])

st.sidebar.markdown("### 📊 初階過濾條件")
price_range = st.sidebar.slider("預算範圍 (股價)", 10, 240, (20, 150))
min_vol = st.sidebar.number_input("成交量 (避免沒人玩)", value=1000, step=500)

params = {'price_min': price_range[0], 'price_max': price_range[1], 'min_volume': min_vol * 1000}

if "右側" in strategy_mode:
    params['min_win_rate'] = st.sidebar.slider("10日收紅K比例 (%)", 30, 90, 40)
    params['vol_burst_ratio'] = st.sidebar.slider("今天人氣 (成交量倍增)", 0.8, 3.0, 1.0)
else:
    params['rsi_threshold'] = st.sidebar.slider("恐慌指數 (越低越便宜)", 10, 50, 30)
    params['bias_threshold'] = st.sidebar.slider("打折程度 (跌幅 %)", 3, 20, 5)

st.title("📈 台股直觀戰情室 (二次篩選版)")

if st.button("🚀 開始全市場掃描", type="primary"):
    with st.spinner("連線證交所..."):
        all_tickers, names_map = get_twse_stock_list()
        
    if not all_tickers: st.stop()
        
    results = []
    bar = st.progress(0)
    status = st.empty()
    
    chunk_size = 20
    chunks = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        status.text(f"分析進度... (掃描至 {names_map.get(chunk[0], chunk[0])})")
        
        try:
            batch = yf.download(chunk, period="2mo", group_by='ticker', progress=False, threads=False)
            for ticker in chunk:
                try:
                    df = batch if len(chunk)==1 else batch.get(ticker)
                    if df is None or df.empty: continue
                    if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                    if 'Close' not in df.columns: continue
                    
                    df = df.dropna(subset=['Close'])
                    df = calculate_indicators(df)
                    
                    match, data = analyze_stock(ticker, names_map.get(ticker, ticker), df, "Right" if "右側" in strategy_mode else "Left", params)
                    if match: results.append(data)
                except: continue
        except: continue
            
    bar.empty()
    status.empty()
    
    if results:
        df_res = pd.DataFrame(results)
        
        # 二次篩選：依照 AI評分 由高到低排序，把真正高勝率的推到最前面
        df_res = df_res.sort_values(by="AI評分", ascending=False)
        
        st.success(f"找到 {len(results)} 檔機會！已依照「爆發力綜合評分」自動排序。")
        
        st.dataframe(
            df_res,
            column_config={
                "代號": st.column_config.TextColumn("代號", width="small"),
                "名稱": st.column_config.TextColumn("名稱", width="small"),
                "AI評分": st.column_config.NumberColumn("🔥 爆發力評分", help="滿分100。考量K線型態、均線乖離與量能的綜合分數", format="%d 分"),
                "現價": st.column_config.NumberColumn("價格", format="$%.2f"),
                "熱度(RSI)": st.column_config.ProgressColumn("溫度計 (RSI)", format="%d", min_value=0, max_value=100),
                "近期勝率(%)": st.column_config.ProgressColumn("近期勝率", help="過去10天收紅K的比例", format="%d%%", min_value=0, max_value=100),
                "AI 簡評": st.column_config.TextColumn("💡 AI 白話點評", width="medium"),
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("沒找到。建議放寬初階過濾條件。")
