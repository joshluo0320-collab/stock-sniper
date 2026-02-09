import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import urllib3

# 1. 關閉惱人的 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 系統設定
# ============================================
st.set_page_config(page_title="台股全市場掃描 (深度分析版)", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000  
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {
        '2337.TW': {'cost': 0, 'shares': 1000} 
    }

# ============================================
# 核心功能：抓取清單與技術指標
# ============================================

@st.cache_data(ttl=86400)
def get_twse_stock_list():
    """從證交所抓取上市股票清單"""
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
        
        if '有價證券代號及名稱' in df.columns:
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
    except Exception:
        return [], {}

def calculate_indicators(df):
    """計算所有技術指標 (RSI, MACD, KD, 布林)"""
    if len(df) < 35: return df
    
    # 1. RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # 2. MACD (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal'] # 柱狀圖

    # 3. KD (9, 3, 3) - 簡單版
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()

    # 4. 均線與布林
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean() # 月線
    df['MA60'] = df['Close'].rolling(window=60).mean() # 季線
    
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Low'] = df['BB_Mid'] - (2 * df['BB_Std'])
    df['BB_High'] = df['BB_Mid'] + (2 * df['BB_Std'])
    
    # 5. 成交量均量
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    return df

def get_position_level(price, ma60, ma240=None):
    """判斷股價位階"""
    if price < ma60: return "低檔整理區"
    elif price > ma60 * 1.2: return "高檔過熱區"
    else: return "中繼攻擊區"

# ============================================
# 篩選與深度分析邏輯
# ============================================
def analyze_stock(ticker, stock_name, df, mode, params):
    if df is None or len(df) < 35: return False, None, 0

    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = last['Close']
    
    # 共同門檻
    if last['Volume'] < params['min_volume']: return False, None, 0
    if not (params['price_min'] <= price <= params['price_max']): return False, None, 0

    reason = []
    score = 0
    
    # --- 指標訊號解讀 ---
    # MACD 訊號
    macd_bull = last['MACD'] > last['Signal']
    macd_cross = (last['MACD'] > last['Signal']) and (prev['MACD'] <= prev['Signal'])
    macd_text = "MACD黃金交叉" if macd_cross else ("MACD多頭" if macd_bull else "MACD空頭")
    
    # RSI 訊號
    rsi_val = last['RSI']
    rsi_status = "過熱" if rsi_val > 70 else ("超賣" if rsi_val < 30 else "中性")

    # 位階訊號
    level = get_position_level(price, last['MA60'])

    # --- A. 右側交易 (順勢) ---
    if mode == 'Right':
        trend_ok = price > last['MA20']
        
        # 勝率計算
        recent = df.iloc[-10:]
        up_days = sum(recent['Close'] >= recent['Open'])
        win_rate = (up_days / 10) * 100
        
        # 量能計算
        vol_ratio = last['Volume'] / last['Vol_MA5'] if last['Vol_MA5'] > 0 else 1.0
        
        if trend_ok and win_rate >= params['min_win_rate'] and vol_ratio >= params['vol_burst_ratio']:
            score = win_rate + (vol_ratio * 10)
            
            # 生成深度分析文案
            reason.append(f"【趨勢】股價站上月線，處於{level}")
            reason.append(f"【動能】10日勝率{int(win_rate)}%，今日爆量{vol_ratio:.1f}倍")
            reason.append(f"【指標】{macd_text}，RSI({rsi_val:.1f}){rsi_status}")
            if macd_cross: reason.append("★ MACD剛轉強，起漲訊號明確")
            
            full_analysis = " | ".join(reason)
            return True, full_analysis, price

    # --- B. 左側交易 (逆勢) ---
    elif mode == 'Left':
        oversold = rsi_val < params['rsi_threshold']
        bias = (price - last['MA20']) / last['MA20'] * 100
        cheap_enough = bias < -params['bias_threshold']
        
        if oversold and cheap_enough:
            reason.append(f"【反彈】RSI({rsi_val:.1f})進入超賣區，負乖離{abs(bias):.1f}%")
            reason.append(f"【位階】{level}，股價回測支撐")
            if last['Close'] <= last['BB_Low'] * 1.02: reason.append("★ 觸碰布林下軌，短線止跌機率高")
            if macd_bull: reason.append("⚠️ 注意：MACD 尚未翻紅，需分批佈局")
            else: reason.append("指標背離醞釀中")
            
            full_analysis = " | ".join(reason)
            return True, full_analysis, price
            
    return False, None, 0

# ============================================
# UI 介面
# ============================================
st.sidebar.header("🕹️ 操盤控制台")

# 資產
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
    params['min_win_rate'] = st.sidebar.slider("10日勝率 (%)", 30, 90, 40)
    params['vol_burst_ratio'] = st.sidebar.slider("攻擊量能 (倍數)", 0.8, 3.0, 1.0)
else:
    params['rsi_threshold'] = st.sidebar.slider("RSI 恐慌值 (<)", 10, 50, 30)
    params['bias_threshold'] = st.sidebar.slider("便宜程度 (負乖離 %)", 3, 20, 5)

# ============================================
# 主程式執行
# ============================================
st.title("📈 台股全市場掃描系統 (深度分析版)")
st.caption("資料來源：證交所上市清單 | 特色：MACD+RSI+位階自動解讀")

# 資產顯示
total_stock_val = 0
try:
    t = yf.Ticker("2337.TW")
    hist = t.history(period="1d")
    if not hist.empty:
        total_stock_val = hist['Close'].iloc[-1] * st.session_state.portfolio['2337.TW']['shares']
except: pass

col1, col2 = st.columns(2)
col1.metric("可用銀彈", f"${int(st.session_state.cash):,}")
col2.metric("庫存市值 (旺宏)", f"${int(total_stock_val):,}")

st.markdown("---")

if st.button("開始掃描 (上市股票)", type="primary"):
    
    with st.spinner("連線證交所更新清單中..."):
        all_tickers, names_map = get_twse_stock_list()
        
    if not all_tickers:
        st.error("無法取得股票清單，請稍後再試。")
        st.stop()
        
    st.info(f"成功取得 {len(all_tickers)} 檔上市股票，開始深度分析...")
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    chunk_size = 20
    chunks = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        current_count = min((i + 1) * chunk_size, len(all_tickers))
        progress_bar.progress((i + 1) / len(chunks))
        status_text.text(f"正在掃描: {current_count}/{len(all_tickers)} (目前分析: {names_map.get(chunk[0], chunk[0])} 等)")
        
        try:
            batch_data = yf.download(chunk, period="3mo", group_by='ticker', progress=False, threads=False)
            
            for ticker in chunk:
                try:
                    if len(chunk) == 1: df = batch_data
                    else: df = batch_data.get(ticker)
                    
                    if df is None or df.empty: continue
                    if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                    if 'Close' not in df.columns: continue
                    
                    df = df.dropna(subset=['Close'])
                    df = calculate_indicators(df)
                    
                    ch_name = names_map.get(ticker, ticker)
                    mode_key = "Right" if "右側" in strategy_mode else "Left"
                    
                    is_match, reason, price = analyze_stock(ticker, ch_name, df, mode_key, params)
                    
                    if is_match:
                        buy_status = "✅ 可買" if price * 1000 <= st.session_state.cash else "❌ 資金不足"
                        results.append({
                            "代號": ticker.replace('.TW', ''),
                            "名稱": ch_name,
                            "現價": round(price, 2),
                            "深度分析報告": reason, # 這裡會顯示完整的分析字串
                            "狀態": buy_status
                        })
                except Exception: continue
        except Exception: continue
            
    progress_bar.empty()
    status_text.empty()
    
    if results:
        st.success(f"掃描完成！共發現 {len(results)} 檔標的。")
        res_df = pd.DataFrame(results)
        
        st.markdown("### 📋 篩選結果與 AI 分析報告")
        st.dataframe(
            res_df, 
            column_config={
                "深度分析報告": st.column_config.TextColumn("📊 AI 技術解讀", width="large", help="包含趨勢、動能與指標的綜合分析")
            },
            use_container_width=True
        )
    else:
        st.warning("掃描完成，無符合條件標的。")

st.markdown("---")
st.subheader("🔍 個股詳細檢查")
check_ticker = st.text_input("輸入代號 (如 2330)", "2337")
if check_ticker:
    if ".TW" not in check_ticker.upper(): check_ticker += ".TW"
    try:
        df_c = yf.download(check_ticker, period="6mo", progress=False)
        if isinstance(df_c.columns, pd.MultiIndex): df_c.columns = df_c.columns.get_level_values(0)
        df_c = calculate_indicators(df_c)
        
        # 建立互動式圖表
        fig = go.Figure()
        
        # K線圖
        fig.add_trace(go.Candlestick(x=df_c.index, open=df_c['Open'], high=df_c['High'], low=df_c['Low'], close=df_c['Close'], name='K線'))
        fig.add_trace(go.Scatter(x=df_c.index, y=df_c['MA20'], line=dict(color='orange', width=1.5), name='月線'))
        fig.add_trace(go.Scatter(x=df_c.index, y=df_c['MA60'], line=dict(color='green', width=1.5), name='季線'))

        # 布林通道
        if "左側" in strategy_mode:
            fig.add_trace(go.Scatter(x=df_c.index, y=df_c['BB_High'], line=dict(color='gray', width=1, dash='dot'), name='布林上軌'))
            fig.add_trace(go.Scatter(x=df_c.index, y=df_c['BB_Low'], line=dict(color='gray', width=1, dash='dot'), name='布林下軌'))
            
        fig.update_layout(title=f"{check_ticker} 走勢圖", xaxis_rangeslider_visible=False, height=500)
        st.plotly_chart(fig, use_container_width=True)
        
        # 顯示當前關鍵指標數據
        last_k = df_c.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("RSI (14)", f"{last_k['RSI']:.1f}")
        c2.metric("MACD柱狀", f"{last_k['Hist']:.2f}", delta_color="normal")
        c3.metric("KD值 (K/D)", f"{last_k['K']:.1f} / {last_k['D']:.1f}")
        c4.metric("乖離率", f"{(last_k['Close']-last_k['MA20'])/last_k['MA20']*100:.1f}%")
        
    except: st.error("查無資料")
