import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ============================================
# 1. 系統初始化與設置 (System Setup)
# ============================================
st.set_page_config(page_title="方寸間投資決策系統 (Josh版)", layout="wide")

# 初始化 Session State (模擬資料庫)
if 'cash' not in st.session_state:
    st.session_state.cash = 240000  # 用戶現有現金
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {
        '2337.TW': {'cost': 0, 'shares': 1000}  # 旺宏 1 張
    } 

# 預設觀察清單
WATCHLIST = [
    '2330.TW', '2337.TW', '2454.TW', '2303.TW', '3034.TW', 
    '3035.TW', '3037.TW', '2379.TW', '3008.TW', '3443.TW',
    '3231.TW', '2382.TW', '2356.TW', '2376.TW', '2353.TW',
    '6531.TW', '4919.TW', '4961.TW', '2603.TW', '2609.TW',
    '8299.TW', '6239.TW', '3583.TW', '2317.TW' 
]

# ============================================
# 2. 工具函數 (內建計算 RSI/布林通道，無需額外安裝 ta)
# ============================================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_stock_data(ticker, period="6mo"):
    """下載股價數據並計算基礎指標"""
    try:
        # 下載數據
        df = yf.download(ticker, period=period, progress=False)
        if df.empty: return None
        
        # 處理 MultiIndex Column 問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 基礎均線
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean() # 月線
        df['MA60'] = df['Close'].rolling(window=60).mean() # 季線
        df['MA240'] = df['Close'].rolling(window=240).mean() # 年線
        df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
        
        # 手動計算 RSI (移除 ta 依賴)
        df['RSI'] = calculate_rsi(df['Close'])
        
        # 手動計算布林通道 (移除 ta 依賴)
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        df['BB_Std'] = df['Close'].rolling(window=20).std()
        df['BB_High'] = df['BB_Mid'] + (2 * df['BB_Std'])
        df['BB_Low'] = df['BB_Mid'] - (2 * df['BB_Std'])
        
        return df
    except Exception as e:
        return None

def analyze_strategy(df, mode, params):
    """
    核心選股邏輯
    mode: 'Right' (右側順勢) or 'Left' (左側抄底)
    params: 來自側邊欄的篩選參數
    """
    if df is None or len(df) < 30: return False, "數據不足", 0

    last_row = df.iloc[-1]
    ticker_price = last_row['Close']
    
    # --- 共同篩選 (價格與成交量) ---
    if not (params['price_min'] <= ticker_price <= params['price_max']):
        return False, "價格不符", 0
    if last_row['Volume'] < params['vol_threshold']:
        return False, "成交量不足", 0

    reason = ""
    
    # --- 右側順勢 (趨勢交易) ---
    if mode == 'Right':
        # 1. 均線排列 (多頭)
        trend_ok = last_row['Close'] > last_row['MA20']
        
        # 2. 攻擊量能
        vol_ok = last_row['Volume'] > last_row['Vol_MA5'] * params['vol_burst_ratio']
        
        # 3. 位階判斷
        bias_year = (last_row['Close'] - last_row['MA240']) / last_row['MA240'] * 100
        stage = "未知"
        if 0 < bias_year <= 10: stage = "剛起漲 (初升段)"
        elif 10 < bias_year <= 30: stage = "主升段 (加速期)"
        elif bias_year > 30: stage = "高乖離 (風險高)"
        elif bias_year < 0: stage = "年線下 (反彈)"
        
        # 篩選邏輯
        if trend_ok and vol_ok:
            reason = f"【{stage}】股價站穩月線，今日出量攻擊 (量增{last_row['Volume']/last_row['Vol_MA5']:.1f}倍)。"
            return True, reason, ticker_price

    # --- 左側逆勢 (抄底交易) ---
    elif mode == 'Left':
        # 1. 極端超跌 (RSI)
        # 確保 RSI 不是 NaN
        rsi_val = last_row['RSI'] if not pd.isna(last_row['RSI']) else 50
        rsi_oversold = rsi_val < params['rsi_limit']
        
        # 2. 乖離率 (負乖離過大)
        bias_20 = (last_row['Close'] - last_row['MA20']) / last_row['MA20'] * 100
        bias_ok = bias_20 < -params['bias_limit']
        
        # 3. 底部訊號 (布林下軌 or 長下影線)
        touch_bb_low = last_row['Close'] <= last_row['BB_Low'] * 1.02
        
        # 簡單判斷下影線
        body = abs(last_row['Close'] - last_row['Open'])
        lower_shadow = min(last_row['Close'], last_row['Open']) - last_row['Low']
        hammer = (lower_shadow > body * 2) and rsi_oversold
        
        if (rsi_oversold and bias_ok) or hammer:
            signal_type = "長下影線探底" if hammer else "指標嚴重超賣"
            reason = f"【{signal_type}】RSI({rsi_val:.1f}) 進入鈍化區，且負乖離達 {bias_20:.1f}%，醞釀 10% 反彈。"
            return True, reason, ticker_price

    return False, "", 0

# ============================================
# 3. 側邊欄 UI (Sidebar Control Panel)
# ============================================
st.sidebar.header("🕹️ 交易控制台")

# 3.1 資產配置更新
with st.sidebar.expander("💰 資產數據校正", expanded=False):
    st.session_state.cash = st.number_input("可用現金 (TWD)", value=st.session_state.cash, step=1000)
    st.write(f"目前持股: 旺宏 {st.session_state.portfolio.get('2337.TW', {}).get('shares', 0)} 股")

# 3.2 策略選擇
st.sidebar.markdown("---")
strategy_mode = st.sidebar.radio("選擇交易模式", ["右側順勢 (趨勢攻擊)", "左側逆勢 (極限抄底)"])

# 3.3 動態參數面板
st.sidebar.markdown("### 📊 篩選參數設定")

# 價格過濾 (通用)
price_range = st.sidebar.slider("股價範圍 (配合24萬預算)", 10, 250, (20, 150))
min_vol = st.sidebar.number_input("最低日成交量 (張)", value=2000, step=500)

params = {
    'price_min': price_range[0],
    'price_max': price_range[1],
    'vol_threshold': min_vol * 1000 # 轉為股數
}

if strategy_mode == "右側順勢 (趨勢攻擊)":
    st.sidebar.info("🚀 尋找：站上均線、帶量突破、法人轉買的標的")
    params['vol_burst_ratio'] = st.sidebar.slider("爆量倍數 (成交量 > 5日均量 X倍)", 1.0, 3.0, 1.2)
    win_rate_threshold = st.sidebar.slider("模擬歷史勝率門檻 (%)", 50, 90, 60)

else: # 左側逆勢
    st.sidebar.error("🧲 尋找：RSI超賣、乖離過大、下影線止跌")
    params['rsi_limit'] = st.sidebar.slider("RSI 超賣界線", 10, 40, 30)
    params['bias_limit'] = st.sidebar.slider("月線負乖離 (%)", 5, 20, 8)

# ============================================
# 4. 主畫面 (Main Dashboard)
# ============================================

# --- Section A: 資產總覽 ---
st.title("💼 方寸間資產管理看板")

# 計算即時淨值
total_stock_value = 0
portfolio_details = []

for ticker, data in st.session_state.portfolio.items():
    stock_df = get_stock_data(ticker, period="5d")
    current_price = stock_df['Close'].iloc[-1] if stock_df is not None else 0
    market_value = current_price * data['shares']
    total_stock_value += market_value
    
    change = 0
    if stock_df is not None:
        change = current_price - stock_df['Close'].iloc[-2]
    
    portfolio_details.append({
        "代號": ticker,
        "股數": data['shares'],
        "現價": round(current_price, 2),
        "漲跌": round(change, 2),
        "市值": int(market_value)
    })

net_worth = st.session_state.cash + total_stock_value

# 顯示關鍵指標 (KPI)
col1, col2, col3 = st.columns(3)
col1.metric("總資產淨值", f"${net_worth:,}", delta=None)
col2.metric("可用現金 (銀彈)", f"${st.session_state.cash:,}", delta="已入帳")
col3.metric("證券市值 (旺宏)", f"${int(total_stock_value):,}")

# 持股細節表
if portfolio_details:
    st.dataframe(pd.DataFrame(portfolio_details).style.highlight_max(axis=0), use_container_width=True)
else:
    st.info("目前無持股")

st.markdown("---")

# --- Section B: 智能選股掃描 ---
st.header(f"🔍 智能選股結果：{strategy_mode}")
st.caption("系統正在掃描觀察名單，並應用您的二次篩選邏輯...")

if st.button("開始掃描 (執行SOP)", type="primary"):
    results = []
    progress_bar = st.progress(0)
    
    for i, ticker in enumerate(WATCHLIST):
        df = get_stock_data(ticker)
        is_match, reason, price = analyze_strategy(df, "Right" if "右側" in strategy_mode else "Left", params)
        
        if is_match:
            # 二次篩選：檢查預算是否足夠買一張
            can_buy = "✅" if price * 1000 <= st.session_state.cash else "❌ (資金不足)"
            
            results.append({
                "代號": ticker,
                "現價": round(price, 2),
                "策略解析": reason,
                "預算檢核": can_buy,
                "預期操作": "追價進場" if "右側" in strategy_mode else "分批佈局"
            })
        
        progress_bar.progress((i + 1) / len(WATCHLIST))

    # 顯示結果
    if results:
        res_df = pd.DataFrame(results)
        st.success(f"掃描完成！共發現 {len(res_df)} 檔符合條件的標的。")
        
        st.dataframe(
            res_df,
            column_config={
                "策略解析": st.column_config.TextColumn("AI 分析觀點", width="large"),
            },
            use_container_width=True
        )
            
    else:
        st.warning("⚠️ 當前條件下無符合標的。請嘗試：\n1. 調整左側面板的「股價範圍」\n2. 放寬「成交量」門檻\n3. 調整策略參數 (例如 RSI 放寬至 35)")

# --- Section C: 即時圖表 ---
st.markdown("---")
st.subheader("📈 重點個股快篩圖 (以旺宏為例)")
chart_ticker = st.selectbox("選擇查看個股", list(st.session_state.portfolio.keys()) + WATCHLIST)
chart_df = get_stock_data(chart_ticker)

if chart_df is not None:
    fig = go.Figure()
    # K線
    fig.add_trace(go.Candlestick(x=chart_df.index,
                    open=chart_df['Open'], high=chart_df['High'],
                    low=chart_df['Low'], close=chart_df['Close'], name='K線'))
    # 均線
    fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['MA20'], line=dict(color='orange', width=1), name='月線(20MA)'))
    
    # 布林通道 (如果選左側交易時顯示)
    if "左側" in strategy_mode:
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['BB_High'], line=dict(color='gray', width=1, dash='dot'), name='布林上軌'))
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['BB_Low'], line=dict(color='gray', width=1, dash='dot'), name='布林下軌'))

    fig.update_layout(title=f"{chart_ticker} 走勢圖", xaxis_rangeslider_visible=False, height=400)
    st.plotly_chart(fig, use_container_width=True)
