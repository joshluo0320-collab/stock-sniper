import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import urllib3
import time

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統初始化
# ============================================
st.set_page_config(page_title="台股上市掃描系統 (防卡死版)", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {
        '2337.TW': {'cost': 0, 'shares': 1000}
    }

# ============================================
# 2. 核心功能：抓取「上市」清單
# ============================================
@st.cache_data(ttl=86400)
def get_twse_stock_list():
    """
    抓取證交所「上市」股票 (Mode=2)
    """
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False, timeout=10) # 設定 10秒 timeout
        
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        # 只留股票
        col_type = '有價證券別'
        if col_type in df.columns:
            df = df[df[col_type] == '股票']
        
        tickers = []
        names_map = {}
        
        col_code_name = '有價證券代號及名稱'
        if col_code_name in df.columns:
            for index, row in df.iterrows():
                code_name = row[col_code_name]
                parts = str(code_name).split()
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    if len(code) == 4 and code.isdigit():
                        ticker = f"{code}.TW"
                        tickers.append(ticker)
                        names_map[ticker] = name
        return tickers, names_map
    except Exception as e:
        st.error(f"清單抓取失敗: {e}")
        return [], {}

def calculate_indicators(df):
    if len(df) < 20: return df
    
    # RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # 均線
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    # 布林通道
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Low'] = df['BB_Mid'] - (2 * df['BB_Std'])
    
    return df

# ============================================
# 3. 篩選邏輯
# ============================================
def analyze_stock(ticker, stock_name, df, mode, params):
    if df is None or len(df) < 30: return False, "", 0
    
    last = df.iloc[-1]
    price = last['Close']
    
    # 基礎過濾
    if last['Volume'] < params['min_volume']: return False, "", 0
    if not (params['price_min'] <= price <= params['price_max']): return False, "", 0

    reason = ""
    display_name = f"{stock_name} ({ticker.replace('.TW', '')})"

    # 右側交易
    if mode == 'Right':
        trend_ok = price > last['MA20']
        
        recent = df.iloc[-10:]
        up_days = sum(recent['Close'] >= recent['Open'])
        win_rate = (up_days / 10) * 100
        win_rate_ok = win_rate >= params['min_win_rate']
        
        vol_val = last['Vol_MA5'] if not pd.isna(last['Vol_MA5']) and last['Vol_MA5'] > 0 else 1
        vol_ratio = last['Volume'] / vol_val
        vol_ok = vol_ratio >= params['vol_burst_ratio']
        
        if trend_ok and win_rate_ok and vol_ok:
            reason = f"【{display_name}】站上月線，10日勝率{int(win_rate)}%，量增{vol_ratio:.1f}倍"
            return True, reason, price

    # 左側交易
    elif mode == 'Left':
        rsi_val = last['RSI'] if not pd.isna(last['RSI']) else 50
        oversold = rsi_val < params['rsi_threshold']
        
        bias = (price - last['MA20']) / last['MA20'] * 100
        cheap_enough = bias < -params['bias_threshold']
        
        if oversold and cheap_enough:
            reason = f"【{display_name}】RSI僅{rsi_val:.1f}，負乖離{abs(bias):.1f}%"
            return True, reason, price
            
    return False, "", 0

# ============================================
# 4. 介面與主程式
# ============================================
st.sidebar.header("🕹️ 操盤控制台")

with st.sidebar.expander("💰 資產狀態", expanded=True):
    st.session_state.cash = st.number_input("可用現金", value=st.session_state.cash, step=1000)
    st.write(f"庫存: 旺宏 {st.session_state.portfolio.get('2337.TW', {}).get('shares', 0)} 股")

st.sidebar.markdown("---")
strategy_mode = st.sidebar.radio("交易策略", ["右側交易 (順勢追漲)", "左側交易 (逆勢抄底)"])

st.sidebar.markdown("### 📊 篩選條件")
price_range = st.sidebar.slider("股價範圍", 10, 240, (20, 150))
min_vol = st.sidebar.number_input("最低成交量 (張)", value=1000, step=500)

params = {
    'price_min': price_range[0],
    'price_max': price_range[1],
    'min_volume': min_vol * 1000
}

if "右側" in strategy_mode:
    st.sidebar.info("🚀 右側策略")
    params['min_win_rate'] = st.sidebar.slider("10日勝率 (%)", 30, 90, 40)
    params['vol_burst_ratio'] = st.sidebar.slider("攻擊量能 (倍數)", 0.8, 3.0, 1.0)
else:
    st.sidebar.warning("🧲 左側策略")
    params['rsi_threshold'] = st.sidebar.slider("RSI 恐慌值 (<)", 10, 50, 30)
    params['bias_threshold'] = st.sidebar.slider("便宜程度 (負乖離 %)", 3, 20, 5)

# 主畫面
st.title("📈 台股上市掃描系統")
st.caption("資料來源：台灣證券交易所 (TWSE) 上市股票")

col1, col2 = st.columns(2)
col1.metric("可用銀彈", f"${int(st.session_state.cash):,}")
try:
    p_last = yf.Ticker("2337.TW").fast_info['last_price']
    val = p_last * st.session_state.portfolio['2337.TW']['shares']
except:
    val = 0
col2.metric("庫存市值 (旺宏)", f"${int(val):,}")

st.markdown("---")

if st.button("開始掃描 (上市股票)", type="primary"):
    
    with st.spinner("正在取得上市清單..."):
        all_tickers, names_map = get_twse_stock_list()
    
    if not all_tickers:
        st.stop()
        
    st.info(f"取得 {len(all_tickers)} 檔上市股票。開始分批掃描 (Batch Scan)...")
    
    results = []
    
    # 將股票分成小批次 (Batch)，每批 50 檔
    batch_size = 50
    batches = [all_tickers[i:i + batch_size] for i in range(0, len(all_tickers), batch_size)]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, batch in enumerate(batches):
        # 顯示進度
        pct = (i + 1) / len(batches)
        progress_bar.progress(pct)
        status_text.text(f"正在分析第 {i+1}/{len(batches)} 批 (範圍: {batch[0]} ~ {batch[-1]})")
        
        try:
            # yfinance 下載數據 (加入 timeout 機制，避免卡死)
            # 注意：yf.download 本身沒有 timeout 參數，這裡是利用 Streamlit 的運行特性
            # 若要更嚴格，建議減少 batch_size (已設為 50)
            data = yf.download(batch, period="2mo", group_by='ticker', progress=False, threads=True)
            
            # 解析數據
            for ticker in batch:
                try:
                    # 處理單檔或多檔的 dataframe 結構差異
                    if len(batch) == 1:
                        df = data
                    else:
                        df = data.get(ticker)
                    
                    if df is None or df.empty: continue
                    
                    # 移除 MultiIndex
                    if isinstance(df.columns, pd.MultiIndex):
                        df = df.droplevel(0, axis=1)
                        
                    if 'Close' not in df.columns: continue
                    
                    # 清洗數據
                    df = df.dropna(subset=['Close'])
                    df = calculate_indicators(df)
                    
                    name = names_map.get(ticker, ticker)
                    mode_key = "Right" if "右側" in strategy_mode else "Left"
                    
                    match, reason, price = analyze_stock(ticker, name, df, mode_key, params)
                    
                    if match:
                        buy_status = "✅" if price * 1000 <= st.session_state.cash else "❌"
                        results.append({
                            "代號": ticker.replace('.TW', ''),
                            "名稱": name,
                            "現價": round(price, 2),
                            "分析理由": reason,
                            "資金": buy_status
                        })
                except:
                    continue # 單檔錯誤跳過
        except Exception as e:
            st.warning(f"第 {i+1} 批次下載逾時或失敗，已跳過。")
            continue
            
    progress_bar.progress(1.0)
    status_text.text("掃描完成！")
    
    if results:
        st.success(f"掃描結束，共發現 {len(results)} 檔標的。")
        st.dataframe(pd.DataFrame(results), use_container_width=True)
    else:
        st.warning("掃描結束，無符合條件標的。")

# 個股檢視器
st.markdown("---")
st.subheader("🔍 個股詳細檢查")
check = st.text_input("輸入代碼 (如 2330)", "2337")
if check:
    if ".TW" not in check.upper(): check += ".TW"
    try:
        df_check = yf.download(check, period="6mo", progress=False)
        if isinstance(df_check.columns, pd.MultiIndex):
            df_check.columns = df_check.columns.get_level_values(0)
        df_check = calculate_indicators(df_check)
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_check.index, open=df_check['Open'], high=df_check['High'], low=df_check['Low'], close=df_check['Close'], name='K線'))
        fig.add_trace(go.Scatter(x=df_check.index, y=df_check['MA20'], line=dict(color='orange'), name='月線'))
        if "左側" in strategy_mode:
            fig.add_trace(go.Scatter(x=df_check.index, y=df_check['BB_Low'], line=dict(color='purple', dash='dot'), name='布林下軌'))
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.error("無法讀取")
