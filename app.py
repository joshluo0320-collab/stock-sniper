import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ============================================
# 1. 系統初始化
# ============================================
st.set_page_config(page_title="台股全市場掃描 (上市版)", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000  
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {
        '2337.TW': {'cost': 0, 'shares': 1000} 
    }

# ============================================
# 2. 核心功能：抓取證交所真實清單 (含中文名)
# ============================================
@st.cache_data(ttl=86400)
def get_twse_stock_list():
    """
    從台灣證券交易所 (TWSE) 抓取真實上市公司清單
    回傳: (tickers_list, names_dict)
    """
    try:
        # 證交所「上市公司」網址 (Mode=2)
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        
        # 讀取 HTML 表格 (encoding='cp950' 是為了解析繁體中文)
        dfs = pd.read_html(url, encoding='cp950')
        df = dfs[0]
        
        # 整理欄位 (前兩列通常是雜訊，設第一列為 Header)
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        # 篩選：有價證券別必須是「股票」 (排除 ETF, 權證, 特別股)
        df = df[df['有價證券別'] == '股票']
        
        tickers = []
        names_map = {}
        
        for index, row in df.iterrows():
            code_name = row['有價證券代號及名稱']
            # 格式通常是 "2330 台積電"
            parts = code_name.split()
            if len(parts) >= 2:
                code = parts[0]
                name = parts[1]
                
                # 確保是 4 碼數字 (防呆)
                if len(code) == 4 and code.isdigit():
                    ticker = f"{code}.TW"
                    tickers.append(ticker)
                    names_map[ticker] = name
                    
        return tickers, names_map
        
    except Exception as e:
        st.error(f"無法從證交所抓取清單，請確認網路連線。錯誤: {e}")
        return [], {}

def calculate_indicators(df):
    """計算技術指標"""
    if len(df) < 20: return df
    
    # RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # 均線
    df['MA20'] = df['Close'].rolling(window=20).mean() # 月線
    
    # 布林通道 (左側交易用)
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Low'] = df['BB_Mid'] - (2 * df['BB_Std'])
    
    # 成交量均量
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    return df

# ============================================
# 3. 篩選邏輯
# ============================================
def analyze_stock(ticker, stock_name, df, mode, params):
    if df is None or len(df) < 30: return False, "", 0

    last = df.iloc[-1]
    price = last['Close']
    
    # 0. 共同門檻：成交量 & 價格
    if last['Volume'] < params['min_volume']:
        return False, "量太小", 0
    if not (params['price_min'] <= price <= params['price_max']):
        return False, "價格不符", 0

    reason = ""
    # 確保顯示中文名稱
    display_name = f"{stock_name}({ticker.replace('.TW', '')})"

    # --- A. 右側交易 (順勢) ---
    if mode == 'Right':
        # 1. 趨勢：股價在月線上
        trend_ok = price > last['MA20']
        
        # 2. 勝率：過去10天收紅天數
        recent = df.iloc[-10:]
        up_days = sum(recent['Close'] >= recent['Open'])
        win_rate = (up_days / 10) * 100
        win_rate_ok = win_rate >= params['min_win_rate']
        
        # 3. 量能：今日量能放大
        if pd.isna(last['Vol_MA5']) or last['Vol_MA5'] == 0:
            vol_ratio = 1.0
        else:
            vol_ratio = last['Volume'] / last['Vol_MA5']
        vol_ok = vol_ratio >= params['vol_burst_ratio']
        
        if trend_ok and win_rate_ok and vol_ok:
            reason = f"【{display_name}】站上月線，10日勝率{int(win_rate)}%，量增{vol_ratio:.1f}倍"
            return True, reason, price

    # --- B. 左側交易 (逆勢) ---
    elif mode == 'Left':
        # 1. RSI 超賣
        rsi_val = last['RSI'] if not pd.isna(last['RSI']) else 50
        oversold = rsi_val < params['rsi_threshold']
        
        # 2. 負乖離 (便宜程度)
        bias = (price - last['MA20']) / last['MA20'] * 100
        cheap_enough = bias < -params['bias_threshold']
        
        if oversold and cheap_enough:
            reason = f"【{display_name}】RSI僅{rsi_val:.1f} (超賣)，低於月線{abs(bias):.1f}%"
            return True, reason, price
            
    return False, "", 0

# ============================================
# 4. 側邊欄 UI
# ============================================
st.sidebar.header("🕹️ 操盤控制台")

# 資產
with st.sidebar.expander("💰 資產狀態", expanded=True):
    st.session_state.cash = st.number_input("可用現金", value=st.session_state.cash, step=1000)
    st.write(f"庫存: 旺宏 {st.session_state.portfolio.get('2337.TW', {}).get('shares', 0)} 股")

st.sidebar.markdown("---")
strategy_mode = st.sidebar.radio("交易策略", ["右側交易 (順勢追漲)", "左側交易 (逆勢抄底)"])

st.sidebar.markdown("### 📊 篩選條件")

price_range = st.sidebar.slider("股價範圍 (配合預算)", 10, 240, (20, 150))
min_vol = st.sidebar.number_input("最低成交量 (張)", value=1000, step=500, help="低於此量視為殭屍股")

params = {
    'price_min': price_range[0],
    'price_max': price_range[1],
    'min_volume': min_vol * 1000
}

if "右側" in strategy_mode:
    st.sidebar.info("🚀 右側策略：順勢操作")
    params['min_win_rate'] = st.sidebar.slider("10日勝率 (%)", 30, 90, 40)
    params['vol_burst_ratio'] = st.sidebar.slider("攻擊量能 (倍數)", 0.8, 3.0, 1.0)
else:
    st.sidebar.warning("🧲 左側策略：逆勢抄底")
    params['rsi_threshold'] = st.sidebar.slider("RSI 恐慌值 (<)", 10, 50, 30)
    params['bias_threshold'] = st.sidebar.slider("便宜程度 (負乖離 %)", 3, 20, 5)

# ============================================
# 5. 主畫面執行
# ============================================
st.title("📈 台股全市場掃描系統")
st.caption("資料來源：台灣證券交易所 (TWSE) 上市普通股清單")

# 資產總覽
total_stock_val = 0
try:
    t = yf.Ticker("2337.TW")
    hist = t.history(period="1d")
    if not hist.empty:
        total_stock_val = hist['Close'].iloc[-1] * st.session_state.portfolio['2337.TW']['shares']
except:
    pass

col1, col2 = st.columns(2)
col1.metric("可用銀彈", f"${int(st.session_state.cash):,}")
col2.metric("庫存市值 (旺宏)", f"${int(total_stock_val):,}")

st.markdown("---")

if st.button("開始掃描 (上市股票)", type="primary"):
    
    with st.spinner("正在從證交所抓取最新股票清單..."):
        # 1. 取得真實清單
        all_tickers, names_map = get_twse_stock_list()
        
    if not all_tickers:
        st.stop()
        
    st.info(f"成功取得 {len(all_tickers)} 檔上市股票。開始分析...")
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 2. 批次下載 (每次 50 檔，避免記憶體爆掉)
    chunk_size = 50
    chunks = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        progress_bar.progress((i + 1) / len(chunks))
        status_text.text(f"掃描進度: {i+1}/{len(chunks)} 批 (目前分析至 {chunk[0]})")
        
        try:
            # 批次下載數據
            batch_data = yf.download(chunk, period="2mo", group_by='ticker', progress=False)
            
            for ticker in chunk:
                try:
                    # 提取單一股票資料
                    if len(chunk) == 1: df = batch_data
                    else: df = batch_data.get(ticker)
                    
                    if df is None or df.empty: continue
                    
                    # 清理 MultiIndex 欄位
                    if isinstance(df.columns, pd.MultiIndex):
                        df = df.droplevel(0, axis=1)
                    
                    # 資料清洗
                    if 'Close' not in df.columns: continue
                    df = df.dropna(subset=['Close'])
                    
                    # 計算指標
                    df = calculate_indicators(df)
                    
                    # 取得中文名稱
                    ch_name = names_map.get(ticker, ticker)
                    
                    # 策略分析
                    mode_key = "Right" if "右側" in strategy_mode else "Left"
                    is_match, reason, price = analyze_stock(ticker, ch_name, df, mode_key, params)
                    
                    if is_match:
                        buy_status = "✅ 可買" if price * 1000 <= st.session_state.cash else "❌ 資金不足"
                        results.append({
                            "代號": ticker.replace('.TW', ''),
                            "名稱": ch_name,
                            "現價": round(price, 2),
                            "分析理由": reason,
                            "狀態": buy_status
                        })
                except:
                    continue
        except:
            continue
            
    progress_bar.empty()
    status_text.empty()
    
    # 3. 顯示結果
    if results:
        st.success(f"掃描完成！共發現 {len(results)} 檔標的。")
        res_df = pd.DataFrame(results)
        
        # 讓代號跟名稱排在前面
        cols = ["代號", "名稱", "現價", "狀態", "分析理由"]
        st.dataframe(res_df[cols], use_container_width=True)
    else:
        st.warning("掃描完成，無符合條件標的。建議放寬「勝率」或「成交量」門檻。")

# 個股檢視
st.markdown("---")
st.subheader("🔍 個股詳細檢查")
check_ticker = st.text_input("輸入代碼 (如 2330)", "2337")
if check_ticker:
    # 自動補 .TW
    if ".TW" not in check_ticker.upper():
        check_ticker = check_ticker + ".TW"
        
    try:
        df_check = yf.download(check_ticker, period="6mo", progress=False)
        if isinstance(df_check.columns, pd.MultiIndex):
            df_check.columns = df_check.columns.get_level_values(0)
        
        df_check = calculate_indicators(df_check)
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_check.index,
                        open=df_check['Open'], high=df_check['High'],
                        low=df_check['Low'], close=df_check['Close'], name='K線'))
        fig.add_trace(go.Scatter(x=df_check.index, y=df_check['MA20'], line=dict(color='orange'), name='月線'))
        if "左側" in strategy_mode:
             fig.add_trace(go.Scatter(x=df_check.index, y=df_check['BB_Low'], line=dict(color='purple', dash='dot'), name='布林下軌'))
             
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.error("查無此股數據")
