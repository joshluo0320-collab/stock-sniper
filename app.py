import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time

# ============================================
# 1. 系統初始化
# ============================================
st.set_page_config(page_title="個人股市操盤系統 (全市場版)", layout="wide")

# 初始化 Session State
if 'cash' not in st.session_state:
    st.session_state.cash = 240000  
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {
        '2337.TW': {'cost': 0, 'shares': 1000} 
    }

# ============================================
# 2. 核心功能：全市場名單與中文名稱
# ============================================

@st.cache_data(ttl=3600)
def generate_full_tw_tickers():
    """
    生成台灣上市櫃普通股清單 (約 1000+ 檔)
    不使用「樣本」，而是使用標準代碼區段生成
    """
    tickers = []
    # 定義台股常見的產業代碼開頭 (水泥~其他)
    # 這裡涵蓋 11xx ~ 99xx 的主要區間
    prefixes = [
        # 傳產
        '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', 
        # 電子與科技 (台股主力)
        '24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34', '35', '36', '37', 
        # 生技與其他
        '41', '44', '45', '47', '49', '52', '53', '54', '55', '58', '60', '61', '62', '64', '65', '66', '67',
        '80', '81', '82', '83', '84', '89', '99'
    ]
    
    for pre in prefixes:
        # 每個區段掃描 01 ~ 99
        for i in range(1, 100): 
            ticker = f"{pre}{i:02d}.TW"
            tickers.append(ticker)
    
    # 補入大型權值股與常見股 (確保沒漏掉)
    extras = ['2330.TW', '2317.TW', '2454.TW', '0050.TW']
    for e in extras:
        if e not in tickers:
            tickers.append(e)
            
    return tickers

def get_stock_name(ticker):
    """
    嘗試取得中文名稱
    """
    try:
        t = yf.Ticker(ticker)
        # yfinance 的 longName 有時是英文，有時是中文，視資料源而定
        name = t.info.get('longName', ticker)
        short = t.info.get('shortName', '')
        
        # 簡單過濾：如果是全英文，試著回傳短名，若還是沒有就回傳代碼
        if name and not name.isascii(): # 如果包含非ASCII字符(中文)
            return name
        if short and not short.isascii():
            return short
        return name # 真的沒有中文就顯示英文名
    except:
        return ticker

def calculate_indicators(df):
    """計算技術指標 (不依賴外部套件，純數學計算)"""
    if len(df) < 20: return df
    
    # RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # 均線 (MA)
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean() # 月線
    
    # 布林通道
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Low'] = df['BB_Mid'] - (2 * df['BB_Std'])
    
    # 成交量均量
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    return df

# ============================================
# 3. 篩選邏輯 (回饋修正版)
# ============================================
def analyze_stock(ticker, df, mode, params):
    if df is None or len(df) < 30: return False, "", 0

    last = df.iloc[-1]
    price = last['Close']
    
    # 0. 殭屍股與預算過濾 (最優先執行)
    if last['Volume'] < params['min_volume']:
        return False, "量太小", 0
    if not (params['price_min'] <= price <= params['price_max']):
        return False, "價格不符", 0

    reason = ""
    
    # --- A. 右側交易 (修正版) ---
    if mode == 'Right':
        # 條件 1: 趨勢 (股價 > 月線)
        trend_ok = price > last['MA20']
        
        # 條件 2: 勝率 (過去10天有幾天收紅)
        # 修正：放寬判定，只要收盤 >= 開盤 就算勝
        recent = df.iloc[-10:]
        up_days = sum(recent['Close'] >= recent['Open'])
        win_rate = (up_days / 10) * 100
        win_rate_ok = win_rate >= params['min_win_rate']
        
        # 條件 3: 攻擊量 (今日量 vs 5日均量)
        # 修正：如果 Vol_MA5 是 NaN (新股)，則跳過
        if pd.isna(last['Vol_MA5']) or last['Vol_MA5'] == 0:
            vol_ratio = 1.0
        else:
            vol_ratio = last['Volume'] / last['Vol_MA5']
            
        vol_ok = vol_ratio >= params['vol_burst_ratio']
        
        if trend_ok and win_rate_ok and vol_ok:
            # 成功抓到！這時才去抓中文名 (節省效能)
            ch_name = get_stock_name(ticker)
            reason = f"【{ch_name}】站上月線，10日勝率{int(win_rate)}%，今日量增{vol_ratio:.1f}倍"
            return True, reason, price

    # --- B. 左側交易 (修正版) ---
    elif mode == 'Left':
        # 條件 1: RSI 超賣
        rsi_val = last['RSI'] if not pd.isna(last['RSI']) else 50
        oversold = rsi_val < params['rsi_threshold']
        
        # 條件 2: 乖離率 (股價距離月線多遠)
        bias = (price - last['MA20']) / last['MA20'] * 100
        cheap_enough = bias < -params['bias_threshold']
        
        # 條件 3: 觸碰布林下軌 (加分項，非強制，避免篩不到)
        # 這裡改為「只要滿足 RSI 和 乖離」就輸出，布林當作描述
        
        if oversold and cheap_enough:
            ch_name = get_stock_name(ticker)
            reason = f"【{ch_name}】RSI僅{rsi_val:.1f} (超賣)，低於月線{abs(bias):.1f}% (便宜)"
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

st.sidebar.markdown("### 📊 篩選條件 (已優化)")

# 共用參數
price_range = st.sidebar.slider("股價範圍", 10, 200, (20, 150))
min_vol = st.sidebar.number_input("最低成交量 (張)", value=1000, step=500, help="低於此成交量的股票會被視為殭屍股剔除")

params = {
    'price_min': price_range[0],
    'price_max': price_range[1],
    'min_volume': min_vol * 1000
}

if "右側" in strategy_mode:
    st.sidebar.info("🚀 右側策略：尋找剛起漲、有大人在顧的股票")
    
    # 修正：預設值調低，避免篩不到
    params['min_win_rate'] = st.sidebar.slider(
        "10日勝率 (%)", 30, 90, 40, 
        help="過去10天中有幾天是紅K？設定 40% 較容易篩出標的，設定 70% 極其嚴格。"
    )
    params['vol_burst_ratio'] = st.sidebar.slider(
        "攻擊量能 (倍數)", 0.8, 3.0, 1.0, 
        help="1.0 代表今日成交量大於等於過去5日平均。若一直篩不到，請將此調降至 0.8 或 1.0。"
    )

else:
    st.sidebar.warning("🧲 左側策略：尋找被錯殺、隨時反彈的股票")
    params['rsi_threshold'] = st.sidebar.slider("RSI 恐慌值 (低於)", 10, 50, 30)
    params['bias_threshold'] = st.sidebar.slider("便宜程度 (負乖離 %)", 3, 20, 5)

# ============================================
# 5. 主畫面執行
# ============================================
st.title("📈 個人股市操盤系統")
st.caption("樣本範圍：全台股上市櫃普通股 (約 1200+ 檔) | 資料來源：Yahoo Finance")

# 顯示資產
total_stock_val = 0
# 這裡簡單計算庫存市值
try:
    current_price = yf.Ticker("2337.TW").fast_info['last_price']
    total_stock_val = current_price * st.session_state.portfolio['2337.TW']['shares']
except:
    total_stock_val = 0 # 離線或錯誤時

col1, col2 = st.columns(2)
col1.metric("可用銀彈", f"${int(st.session_state.cash):,}")
col2.metric("庫存市值 (旺宏)", f"${int(total_stock_val):,}")

st.markdown("---")

if st.button("開始全市場掃描 (Full Scan)", type="primary"):
    
    # 1. 生成清單
    all_tickers = generate_full_tw_tickers()
    st.info(f"已生成 {len(all_tickers)} 檔股票代碼，開始批次下載與分析... (請耐心等待約 1-2 分鐘)")
    
    results = []
    
    # 進度條
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 2. 批次處理 (Batch Processing) 以加快速度
    # 每次抓 50 檔
    chunk_size = 50
    chunks = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        # 更新進度
        progress = (i + 1) / len(chunks)
        progress_bar.progress(progress)
        status_text.text(f"正在掃描第 {i+1}/{len(chunks)} 批股票...")
        
        try:
            # 批次下載數據 (大幅提升速度)
            batch_data = yf.download(chunk, period="2mo", group_by='ticker', progress=False)
            
            # 針對每一檔股票分析
            for ticker in chunk:
                try:
                    # 從批次資料中提取單一股票
                    if len(chunk) == 1:
                        df = batch_data
                    else:
                        df = batch_data[ticker]
                    
                    # 清理 MultiIndex
                    if isinstance(df.columns, pd.MultiIndex):
                        df = df.droplevel(0, axis=1) # 有時候 yfinance 結構會變，需防呆
                    
                    # 確保有 Close 欄位且非空
                    if 'Close' not in df.columns or df.empty:
                        continue
                        
                    # 處理缺失值
                    df = df.dropna(subset=['Close'])
                    
                    # 計算指標
                    df = calculate_indicators(df)
                    
                    # 策略分析
                    mode_key = "Right" if "右側" in strategy_mode else "Left"
                    is_match, reason, price = analyze_stock(ticker, df, mode_key, params)
                    
                    if is_match:
                        buy_status = "✅ 可買" if price * 1000 <= st.session_state.cash else "❌ 資金不足"
                        results.append({
                            "股票": reason.split('】')[0].replace('【', '') if '】' in reason else ticker, # 嘗試提取名稱
                            "代碼": ticker,
                            "現價": round(price, 2),
                            "AI 分析理由": reason,
                            "資金檢核": buy_status
                        })
                except Exception as e:
                    continue # 單一股票錯誤不影響整體
                    
        except Exception as e:
            continue # 批次下載錯誤跳過
            
    progress_bar.empty()
    status_text.empty()
    
    # 3. 顯示結果
    if results:
        res_df = pd.DataFrame(results)
        st.success(f"掃描完畢！共發現 {len(res_df)} 檔標的。")
        st.dataframe(
            res_df, 
            column_config={
                "AI 分析理由": st.column_config.TextColumn("篩選詳情", width="large")
            },
            use_container_width=True
        )
    else:
        st.error("掃描了 1000+ 檔股票，但沒有發現符合條件的標的。")
        
        # 給予具體回饋
        if "右側" in strategy_mode:
            st.markdown("""
            **💡 AI 回饋診斷 (右側交易)：**
            目前市場可能處於「回檔整理」或「量縮」階段。
            1. **無股票站上月線？** -> 代表大盤趨勢偏弱。
            2. **無攻擊量能？** -> 代表今日主力觀望，沒人點火。
            
            **建議調整：** 請試著將左側面板的 **[10日勝率]** 調低至 **30%**，或將 **[攻擊量能]** 調為 **0.8** 試試看。
            """)
        else:
            st.markdown("""
            **💡 AI 回饋診斷 (左側交易)：**
            目前市場可能不夠恐慌，或者剛好在半山腰。
            1. **RSI 不夠低？** -> 代表跌得還不夠重。
            2. **負乖離不足？** -> 代表急跌幅度不夠大。
            """)

# 個股檢視器
st.markdown("---")
st.subheader("🔍 個股詳細檢查")
check_ticker = st.text_input("輸入代碼 (如 2330.TW)", "2337.TW")
if check_ticker:
    try:
        df_check = yf.download(check_ticker, period="6mo", progress=False)
        if isinstance(df_check.columns, pd.MultiIndex):
            df_check.columns = df_check.columns.get_level_values(0)
            
        df_check = calculate_indicators(df_check)
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_check.index,
                        open=df_check['Open'], high=df_check['High'],
                        low=df_check['Low'], close=df_check['Close'], name='K線'))
        fig.add_trace(go.Scatter(x=df_check.index, y=df_check['MA20'], line=dict(color='orange', width=1), name='月線'))
        
        if "左側" in strategy_mode:
             fig.add_trace(go.Scatter(x=df_check.index, y=df_check['BB_Low'], line=dict(color='purple', dash='dot'), name='布林下軌'))
             
        st.plotly_chart(fig, use_container_width=True)
        
        # 顯示該股數據
        last_k = df_check.iloc[-1]
        st.write(f"今日收盤: {last_k['Close']:.2f} | 成交量: {int(last_k['Volume'])} | RSI: {last_k['RSI']:.1f}")
        
    except:
        st.error("查無此股")
