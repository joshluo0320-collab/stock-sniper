import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import urllib3

# 1. 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 系統設定
# ============================================
st.set_page_config(page_title="台股直觀分析系統", layout="wide")

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
    """抓取證交所清單"""
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
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # 均線
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
    # 成交量
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    return df

# ============================================
# 白話文翻譯模組 (Novice Translator)
# ============================================
def get_human_status(mode, price, ma20, rsi, macd, signal, win_rate):
    """將技術指標翻譯成新手看的懂的圖示與文字"""
    
    # 1. 趨勢訊號
    trend_icon = "➖ 盤整"
    if price > ma20: trend_icon = "📈 走強"
    if price < ma20: trend_icon = "📉 走弱"
    
    # 2. MACD 動能
    macd_msg = ""
    if macd > signal: macd_msg = "🔥 主力在推"
    else: macd_msg = "🧊 主力休息"
    
    # 3. 綜合評語
    comment = ""
    if mode == 'Right':
        if win_rate > 60: comment = "氣勢正旺，適合順風搭車"
        else: comment = "剛開始轉強，還有空間"
    else:
        if rsi < 20: comment = "跌無可跌，隨時會反彈"
        elif rsi < 35: comment = "價格很甜，適合分批撿便宜"
        
    return trend_icon, macd_msg, comment

# ============================================
# 篩選邏輯
# ============================================
def analyze_stock(ticker, stock_name, df, mode, params):
    if df is None or len(df) < 35: return False, None
    
    last = df.iloc[-1]
    price = last['Close']
    
    # 基礎過濾
    if last['Volume'] < params['min_volume']: return False, None
    if not (params['price_min'] <= price <= params['price_max']): return False, None

    # 取值
    rsi_val = last['RSI'] if not pd.isna(last['RSI']) else 50
    ma20 = last['MA20']
    
    # 計算勝率
    recent = df.iloc[-10:]
    up_days = sum(recent['Close'] >= recent['Open'])
    win_rate = (up_days / 10) * 100
    
    # 量能倍數
    vol_ratio = last['Volume'] / last['Vol_MA5'] if last['Vol_MA5'] > 0 else 1.0

    # --- 策略判斷 ---
    is_match = False
    
    if mode == 'Right': # 右側
        trend_ok = price > ma20
        win_ok = win_rate >= params['min_win_rate']
        vol_ok = vol_ratio >= params['vol_burst_ratio']
        if trend_ok and win_ok and vol_ok: is_match = True
            
    elif mode == 'Left': # 左側
        oversold = rsi_val < params['rsi_threshold']
        bias = (price - ma20) / ma20 * 100
        cheap_enough = bias < -params['bias_threshold']
        if oversold and cheap_enough: is_match = True

    # --- 打包數據 ---
    if is_match:
        # 取得白話文翻譯
        t_icon, m_msg, simple_comment = get_human_status(
            mode, price, ma20, rsi_val, last['MACD'], last['Signal'], win_rate
        )
        
        return True, {
            "代號": ticker.replace('.TW', ''),
            "名稱": stock_name,
            "現價": price,
            "趨勢": t_icon,        # 📈
            "主力動向": m_msg,     # 🔥
            "熱度(RSI)": rsi_val,  # 用於進度條
            "勝率(%)": win_rate/100, # 用於進度條 (0.0~1.0)
            "量能倍數": f"{vol_ratio:.1f}倍",
            "AI 簡評": simple_comment,
            "資金": "✅" if price*1000 <= st.session_state.cash else "❌"
        }
        
    return False, None

# ============================================
# UI 介面
# ============================================
st.sidebar.header("🕹️ 操盤控制台")

with st.sidebar.expander("💰 資產狀態", expanded=True):
    st.session_state.cash = st.number_input("可用現金", value=st.session_state.cash, step=1000)
    st.write(f"庫存: 旺宏 {st.session_state.portfolio.get('2337.TW', {}).get('shares', 0)} 股")

st.sidebar.markdown("---")
strategy_mode = st.sidebar.radio("交易策略", ["右側交易 (順勢追漲)", "左側交易 (逆勢抄底)"])

st.sidebar.markdown("### 📊 簡單設定")
price_range = st.sidebar.slider("預算範圍 (股價)", 10, 240, (20, 150))
min_vol = st.sidebar.number_input("成交量 (避免沒人玩)", value=1000, step=500)

params = {'price_min': price_range[0], 'price_max': price_range[1], 'min_volume': min_vol * 1000}

if "右側" in strategy_mode:
    params['min_win_rate'] = st.sidebar.slider("最近勝率 (紅K越多越好)", 30, 90, 40)
    params['vol_burst_ratio'] = st.sidebar.slider("今天人氣 (成交量倍增)", 0.8, 3.0, 1.0)
else:
    params['rsi_threshold'] = st.sidebar.slider("恐慌指數 (越低越便宜)", 10, 50, 30)
    params['bias_threshold'] = st.sidebar.slider("打折程度 (跌幅 %)", 3, 20, 5)

# ============================================
# 主程式
# ============================================
st.title("📈 台股直觀戰情室")
st.caption("全市場掃描 | 新手友善模式")

# 資產
total_stock_val = 0
try:
    t = yf.Ticker("2337.TW")
    hist = t.history(period="1d")
    if not hist.empty: total_stock_val = hist['Close'].iloc[-1] * 1000
except: pass

c1, c2 = st.columns(2)
c1.metric("💰 可用銀彈", f"${int(st.session_state.cash):,}")
c2.metric("📦 庫存市值", f"${int(total_stock_val):,}")

st.markdown("---")

if st.button("🚀 開始掃描 (上市股票)", type="primary"):
    
    with st.spinner("正在連線證交所..."):
        all_tickers, names_map = get_twse_stock_list()
        
    if not all_tickers:
        st.error("連線失敗")
        st.stop()
        
    st.info(f"鎖定 {len(all_tickers)} 檔股票，AI 分析中...")
    
    results = []
    bar = st.progress(0)
    status = st.empty()
    
    chunk_size = 20
    chunks = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        status.text(f"掃描中: {names_map.get(chunk[0], chunk[0])} ...")
        
        try:
            batch = yf.download(chunk, period="3mo", group_by='ticker', progress=False, threads=False)
            
            for ticker in chunk:
                try:
                    if len(chunk)==1: df = batch
                    else: df = batch.get(ticker)
                    
                    if df is None or df.empty: continue
                    if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                    if 'Close' not in df.columns: continue
                    
                    df = df.dropna(subset=['Close'])
                    df = calculate_indicators(df)
                    
                    name = names_map.get(ticker, ticker)
                    mode_key = "Right" if "右側" in strategy_mode else "Left"
                    
                    match, data = analyze_stock(ticker, name, df, mode_key, params)
                    if match: results.append(data)
                        
                except: continue
        except: continue
            
    bar.empty()
    status.empty()
    
    if results:
        st.success(f"找到 {len(results)} 檔機會！")
        df_res = pd.DataFrame(results)
        
        # --- 重點：設定直觀的視覺化欄位 ---
        st.dataframe(
            df_res,
            column_config={
                "代號": st.column_config.TextColumn("代號", width="small"),
                "名稱": st.column_config.TextColumn("股票名稱", width="medium"),
                "現價": st.column_config.NumberColumn("價格", format="$%.2f"),
                
                # 熱度計：直觀顯示是否過熱
                "熱度(RSI)": st.column_config.ProgressColumn(
                    "溫度計 (RSI)",
                    help="藍色=冷/便宜，紅色=熱/貴",
                    format="%d",
                    min_value=0,
                    max_value=100,
                ),
                # 勝率條：直觀顯示強弱
                "勝率(%)": st.column_config.ProgressColumn(
                    "近期勝率",
                    help="紅色越長代表最近越常漲",
                    format="%.0f%%",
                    min_value=0,
                    max_value=1,
                ),
                "AI 簡評": st.column_config.TextColumn("💡 AI 白話點評", width="large"),
                "資金": st.column_config.TextColumn("預算", width="small"),
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("沒找到。建議放寬「勝率」或「成交量」條件。")

st.markdown("---")
st.subheader("🔍 個股檢查儀")
check = st.text_input("輸入代號 (如 2330)", "2337")
if check:
    if ".TW" not in check.upper(): check += ".TW"
    try:
        df_c = yf.download(check, period="6mo", progress=False)
        if isinstance(df_c.columns, pd.MultiIndex): df_c.columns = df_c.columns.get_level_values(0)
        df_c = calculate_indicators(df_c)
        
        # 繪圖
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_c.index, open=df_c['Open'], high=df_c['High'], low=df_c['Low'], close=df_c['Close'], name='K線'))
        fig.add_trace(go.Scatter(x=df_c.index, y=df_c['MA20'], line=dict(color='orange'), name='月線'))
        
        # 直觀的標題
        last_p = df_c['Close'].iloc[-1]
        last_rsi = df_c['RSI'].iloc[-1]
        rsi_state = "🔥 過熱" if last_rsi > 70 else ("🧊 便宜" if last_rsi < 30 else "⚖️ 正常")
        
        fig.update_layout(
            title=f"📊 {check} 目前 {last_p:.1f} 元 | 狀態：{rsi_state} (RSI={last_rsi:.1f})",
            height=400,
            xaxis_rangeslider_visible=False
        )
        st.plotly_chart(fig, use_container_width=True)
        
    except: st.error("查無資料")
