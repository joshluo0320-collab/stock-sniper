import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ============================================
# 1. 系統初始化與設定
# ============================================
st.set_page_config(page_title="個人股市操盤系統", layout="wide")

# 初始化 Session State
if 'cash' not in st.session_state:
    st.session_state.cash = 240000  # 預設現金
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {
        '2337.TW': {'cost': 0, 'shares': 1000}  # 僅持有旺宏
    }

# ============================================
# 2. 核心功能函數
# ============================================

# 產生台灣股市代碼清單 (模擬全市場)
@st.cache_data
def get_tw_stock_list():
    # 這裡建立一個常見的台股代碼範圍
    # 包含了水泥(11)、食品(12)、塑膠(13)、紡織(14)、電機(15)、電器(16)、化學(17)
    # 玻璃(18)、紙(19)、鋼鐵(20)、橡膠(21)、汽車(22)、電子(23, 24, 3xxx, 4xxx, 6xxx, 8xxx) 等
    # 為了演示效能，這裡先列出主要區段，實際掃描會依賴迴圈
    prefixes = [
        '11', '12', '13', '14', '15', '16', '17', '18', '19', 
        '20', '21', '22', '23', '24', '25', '26', '27', '28', '29',
        '30', '31', '32', '33', '34', '35', '36', '37', 
        '41', '45', '47', '49', 
        '52', '53', '54', '55', '58', 
        '61', '62', '64', '65', '66',
        '80', '81', '82', '83', '84', '99'
    ]
    
    stock_list = []
    # 每個區段抓前 30 檔熱門股作為樣本 (為了避免 demo 跑太久)
    # 若要全市場，邏輯需改為遍歷 00-99，但 yfinance 會很慢
    for pre in prefixes:
        for i in range(1, 40): # 掃描區段內的 x01 ~ x40
            ticker = f"{pre}{i:02d}.TW"
            stock_list.append(ticker)
            
    return stock_list

def calculate_indicators(df):
    """計算技術指標 (不依賴外部 TA 套件)"""
    # RSI (相對強弱指標)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # 均線 (MA)
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean() # 月線
    df['MA60'] = df['Close'].rolling(window=60).mean() # 季線
    
    # 布林通道 (Bollinger Bands)
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Low'] = df['BB_Mid'] - (2 * df['BB_Std'])
    
    # 成交量均量
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    return df

def analyze_stock(ticker, df, mode, params):
    """選股邏輯核心"""
    if df is None or len(df) < 60: return False, "", 0

    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = last['Close']
    
    # --- 共同基本篩選 ---
    # 1. 價格區間 (預算考量)
    if not (params['price_min'] <= price <= params['price_max']):
        return False, "價格不符", 0
    # 2. 殭屍股過濾 (今日成交量)
    if last['Volume'] < params['min_volume']:
        return False, "成交量過低 (殭屍股風險)", 0

    reason = ""
    
    # --- A. 右側交易 (順勢追漲) ---
    if mode == 'Right':
        # 1. 趨勢判斷：股價是否在月線之上 (生命線)
        trend_ok = price > last['MA20']
        
        # 2. 近期勝率 (過去10天有幾天是漲的)
        # 簡單計算：過去10根K線，收盤價 > 開盤價 的天數
        recent_10_days = df.iloc[-10:]
        up_days = sum(recent_10_days['Close'] > recent_10_days['Open'])
        win_rate = (up_days / 10) * 100
        
        win_rate_ok = win_rate >= params['min_win_rate']
        
        # 3. 攻擊訊號 (出量)
        vol_burst = last['Volume'] > last['Vol_MA5'] * params['vol_burst_ratio']
        
        if trend_ok and win_rate_ok and vol_burst:
            reason = f"【多頭啟動】股價站上月線，且過去10天有 {int(win_rate)}% 時間上漲，今日帶量攻擊。"
            return True, reason, price

    # --- B. 左側交易 (逆勢抄底) ---
    elif mode == 'Left':
        # 1. 恐慌指數 (RSI) - 是否超賣
        rsi_val = last['RSI'] if not pd.isna(last['RSI']) else 50
        oversold = rsi_val < params['rsi_threshold']
        
        # 2. 便宜程度 (乖離率) - 跌得夠不夠深
        # 負乖離：股價比月線便宜多少 %
        bias = (price - last['MA20']) / last['MA20'] * 100
        cheap_enough = bias < -params['bias_threshold']
        
        # 3. 止跌跡象 (布林下軌支撐)
        # 股價觸碰到布林通道下緣，通常是短線超跌區
        touch_low = price <= last['BB_Low'] * 1.05 # 接近下軌 5% 範圍內
        
        if oversold and cheap_enough:
            reason = f"【超跌反彈】恐慌指數(RSI)僅 {rsi_val:.1f}，股價低於月線 {abs(bias):.1f}%，具備反彈空間。"
            return True, reason, price
            
    return False, "", 0

# ============================================
# 3. 側邊欄控制面板
# ============================================
st.sidebar.header("🕹️ 操盤控制台")

# 3.1 資產
with st.sidebar.expander("💰 資產狀態", expanded=True):
    st.session_state.cash = st.number_input("可用現金 (TWD)", value=st.session_state.cash, step=1000)
    st.write(f"目前庫存: 旺宏 {st.session_state.portfolio.get('2337.TW', {}).get('shares', 0)} 股")

st.sidebar.markdown("---")

# 3.2 模式選擇
strategy_mode = st.sidebar.radio("交易策略模式", ["右側交易 (順勢追漲)", "左側交易 (逆勢抄底)"])

# 3.3 篩選參數
st.sidebar.markdown("### 📊 篩選條件設定")

# 全域設定
scan_limit = st.sidebar.slider("掃描樣本數 (若跑太慢請調低)", 50, 1500, 200, help="從台灣股市代碼清單中，要隨機掃描多少檔股票。若要全掃請拉到最大。")
price_range = st.sidebar.slider("股價範圍 (預算篩選)", 10, 200, (20, 150))
min_vol_input = st.sidebar.number_input("每日成交量門檻 (張)", value=2000, step=500, help="避免買到沒人玩的殭屍股，建議至少 1000 張以上")

params = {
    'price_min': price_range[0],
    'price_max': price_range[1],
    'min_volume': min_vol_input * 1000
}

if "右側" in strategy_mode:
    st.sidebar.success("🚀 右側策略：買在大家都在買的時候")
    
    # 右側專屬參數
    params['min_win_rate'] = st.sidebar.slider(
        "10日勝率 (%)", 
        min_value=30, max_value=90, value=50, 
        help="過去 10 天內，紅K棒(上漲)出現的機率。設定 40% 表示允許震盪，設定 70% 表示只抓強勢股。"
    )
    
    params['vol_burst_ratio'] = st.sidebar.slider(
        "攻擊量能倍數", 
        min_value=1.0, max_value=3.0, value=1.2, 
        help="今天的成交量是平常(5日均量)的幾倍？1.5倍代表資金湧入。"
    )

else:
    st.sidebar.warning("🧲 左側策略：買在大家恐慌拋售的時候")
    
    # 左側專屬參數
    params['rsi_threshold'] = st.sidebar.slider(
        "恐慌指數 (RSI) 低於", 
        min_value=10, max_value=40, value=30, 
        help="數值越低代表市場越恐慌，通常 < 30 代表超賣，隨時可能反彈。"
    )
    
    params['bias_threshold'] = st.sidebar.slider(
        "便宜程度 (負乖離 %)", 
        min_value=5, max_value=20, value=8, 
        help="股價現在比「月線成本」便宜多少百分比？跌得越深，反彈力道可能越強。"
    )

# ============================================
# 4. 主畫面 Dashboard
# ============================================
st.title("📈 個人股市操盤系統")

# 資產總覽
total_stock_val = 0
for t, d in st.session_state.portfolio.items():
    # 簡單抓一下現價
    try:
        tmp_df = yf.Ticker(t).history(period="1d")
        if not tmp_df.empty:
            p = tmp_df['Close'].iloc[-1]
            total_stock_val += p * d['shares']
    except:
        pass

col1, col2, col3 = st.columns(3)
col1.metric("總資產 (現金+庫存)", f"${int(st.session_state.cash + total_stock_val):,}")
col2.metric("可用銀彈", f"${int(st.session_state.cash):,}")
col3.metric("庫存市值", f"${int(total_stock_val):,}")

st.markdown("---")

# 執行掃描
st.header(f"🔍 執行篩選：{strategy_mode}")
st.caption(f"目標樣本：台灣上市股票 (掃描前 {scan_limit} 檔代碼)")

if st.button("開始全市場掃描", type="primary"):
    # 取得代碼列表
    full_tickers = get_tw_stock_list()
    # 截斷列表以符合使用者設定的限制 (避免等待過久)
    target_tickers = full_tickers[:scan_limit]
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticker in enumerate(target_tickers):
        # 更新進度條
        progress = (i + 1) / len(target_tickers)
        progress_bar.progress(progress)
        status_text.text(f"正在分析: {ticker} ({i+1}/{len(target_tickers)})")
        
        try:
            # 下載數據 (只抓最近 3 個月以加快速度)
            df = yf.download(ticker, period="3mo", progress=False)
            
            # 處理資料結構
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            if not df.empty and len(df) > 20:
                # 計算指標
                df = calculate_indicators(df)
                
                # 判斷策略
                mode_key = "Right" if "右側" in strategy_mode else "Left"
                is_match, reason, price = analyze_stock(ticker, df, mode_key, params)
                
                if is_match:
                    # 預算檢核
                    can_buy = "✅ 可買" if price * 1000 <= st.session_state.cash else "❌ 資金不足"
                    
                    results.append({
                        "代號": ticker,
                        "現價": round(price, 2),
                        "AI 分析理由": reason,
                        "資金狀態": can_buy
                    })
        except Exception as e:
            continue
            
    progress_bar.empty()
    status_text.empty()
    
    if results:
        st.success(f"掃描完成！從 {len(target_tickers)} 檔股票中，發現 {len(results)} 檔符合條件。")
        st.dataframe(
            pd.DataFrame(results), 
            column_config={
                "AI 分析理由": st.column_config.TextColumn("篩選理由", width="large")
            },
            use_container_width=True
        )
    else:
        st.warning("掃描完成，但沒有發現符合條件的股票。建議：\n1. 放寬「每日成交量」\n2. (右側) 降低「10日勝率」門檻\n3. (左側) 降低「乖離率」要求")

# 簡單圖表查看器
st.markdown("---")
st.subheader("📊 個股走勢檢視")
view_ticker = st.text_input("輸入代號 (例如 2330.TW)", "2337.TW")
if view_ticker:
    try:
        v_df = yf.download(view_ticker, period="6mo", progress=False)
        if isinstance(v_df.columns, pd.MultiIndex):
            v_df.columns = v_df.columns.get_level_values(0)
            
        if not v_df.empty:
            v_df = calculate_indicators(v_df)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=v_df.index,
                            open=v_df['Open'], high=v_df['High'],
                            low=v_df['Low'], close=v_df['Close'], name='K線'))
            fig.add_trace(go.Scatter(x=v_df.index, y=v_df['MA20'], line=dict(color='orange', width=1), name='月線'))
            
            # 若是左側交易，顯示布林通道
            if "左側" in strategy_mode:
                fig.add_trace(go.Scatter(x=v_df.index, y=v_df['BB_Low'], line=dict(color='gray', dash='dot'), name='抄底線(布林下軌)'))
                
            fig.update_layout(title=f"{view_ticker} 走勢圖", xaxis_rangeslider_visible=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
    except:
        st.error("無法讀取該股票數據，請確認代號正確。")
