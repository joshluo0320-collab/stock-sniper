import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import plotly.graph_objects as go
from datetime import datetime, timedelta
import urllib3

# 忽略 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. 頁面設定
# ==========================================
st.set_page_config(
    page_title="Josh 的狙擊手戰情室 (回測版)",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎯 Josh 的股市狙擊手戰情室")
st.markdown("### 專屬策略：多頭排列 + 爆量 + RSI 強勢 + **歷史勝率分析**")

# ==========================================
# 2. 側邊欄：參數設定
# ==========================================
st.sidebar.header("⚙️ 策略參數設定")

min_volume = st.sidebar.number_input("最低成交量 (張)", value=800, step=100)
vol_ratio = st.sidebar.slider("爆量係數 (今日 > N倍均量)", 1.0, 3.0, 1.2, 0.1)
rsi_min = st.sidebar.slider("RSI 最低門檻", 30, 70, 55)
rsi_max = st.sidebar.slider("RSI 最高門檻 (避免過熱)", 70, 100, 85)
ma_short = st.sidebar.number_input("短期均線 (MA)", value=20)
ma_long = st.sidebar.number_input("長期均線 (MA)", value=60)

st.sidebar.markdown("---")
st.sidebar.info(
    """
    **📊 勝率分析定義**
    * **回測期間**：過去 1 年 (250個交易日)
    * **訊號定義**：當股價站上月線 + RSI強勢時
    * **獲利目標**：10個交易日(半個月)內，最高價曾觸及 +10%
    """
)

# ==========================================
# 3. 核心函數
# ==========================================

@st.cache_data(ttl=86400)
def get_tw_stock_list():
    """自動抓取證交所最新清單"""
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False)
        html_data = io.StringIO(res.text)
        df = pd.read_html(html_data)[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df['有價證券代號及名稱'] = df['有價證券代號及名稱'].astype(str).str.replace('　', ' ')
        df[['代號', '名稱']] = df['有價證券代號及名稱'].str.split(pat=' ', n=1, expand=True)
        df = df[df['代號'].str.len() == 4]
        df['代號'] = df['代號'].astype(str).str.zfill(4)
        return df[['代號', '名稱']]
    except Exception as e:
        st.error(f"抓取股票清單失敗: {e}")
        return pd.DataFrame()

def get_stock_data(tickers):
    """下載數據 (抓取 300 天以進行回測)"""
    try:
        data = yf.download(tickers, period="300d", interval="1d", group_by='ticker', threads=True, progress=False)
        return data
    except Exception:
        return pd.DataFrame()

def calculate_indicators(df):
    """計算技術指標"""
    df['MA20'] = df['Close'].rolling(window=ma_short).mean()
    df['MA60'] = df['Close'].rolling(window=ma_long).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    # RSI
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / ema_down
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['High60'] = df['Close'].rolling(window=60).max()
    return df

def calculate_win_rate(df):
    """
    計算歷史勝率：
    過去一年內，當出現類似買點時，
    10天內(半個月)是否曾達到 +10% 獲利?
    """
    try:
        # 為了避免資料不足，從第 60 天開始回測
        start_idx = 60
        end_idx = len(df) - 10 # 最後10天因為還沒發生未來，無法驗證，所以扣掉
        
        wins = 0
        total_signals = 0
        
        # 掃描過去的每一天 (模擬歷史交易)
        for i in range(start_idx, end_idx):
            row = df.iloc[i]
            
            # 簡易版進場條件 (模擬當初的強勢狀態)
            # 條件：收盤 > MA20 且 RSI > 55 (代表趨勢轉強)
            if row['Close'] > row['MA20'] and row['RSI'] > 55:
                total_signals += 1
                
                # 檢查接下來 10 天的最高價
                entry_price = row['Close']
                target_price = entry_price * 1.10 # 目標 +10%
                
                # 往後看 10 天
                future_10_days = df.iloc[i+1 : i+11]
                max_price = future_10_days['High'].max()
                
                if max_price >= target_price:
                    wins += 1
        
        if total_signals == 0:
            return "N/A" # 無訊號
            
        win_rate = (wins / total_signals) * 100
        return round(win_rate, 1)
        
    except Exception:
        return "N/A"

# ==========================================
# 4. 主程式邏輯
# ==========================================

with st.spinner("正在更新全台股票清單..."):
    stock_list_df = get_tw_stock_list()

if stock_list_df.empty:
    st.stop()

if st.button("🚀 啟動全市場掃描 + 勝率回測"):
    
    st.write("正在掃描市場並進行歷史模擬，請耐心等候...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    stock_map = dict(zip(stock_list_df['代號'], stock_list_df['名稱']))
    tickers = [f"{x}.TW" for x in stock_list_df['代號'].tolist()]
    
    chunk_size = 30 # 調小批次量，避免記憶體不足
    total = len(tickers)
    results = []
    
    for i in range(0, total, chunk_size):
        chunk = tickers[i : i + chunk_size]
        progress = min((i + chunk_size) / total, 1.0)
        progress_bar.progress(progress)
        status_text.text(f"掃描進度：{i}/{total} ...")
        
        data = get_stock_data(chunk)
        
        if not data.empty:
            for ticker in chunk:
                try:
                    if len(chunk) == 1:
                        df = data
                    else:
                        if ticker not in data.columns.levels[0]: continue
                        df = data[ticker].copy()
                    
                    df = df.dropna(subset=['Close'])
                    if len(df) < 100: continue # 資料太短不回測
                    
                    df = calculate_indicators(df)
                    latest = df.iloc[-1]
                    
                    # 取值
                    close = float(latest['Close'])
                    ma20 = float(latest['MA20'])
                    ma60 = float(latest['MA60'])
                    vol = int(float(latest['Volume']) / 1000)
                    vol_ma5 = int(float(latest['Vol_MA5']) / 1000)
                    rsi = float(latest['RSI'])
                    high60 = float(latest['High60'])
                    
                    # 篩選邏輯
                    cond1 = (close > ma20) and (ma20 > ma60)
                    cond2 = vol >= min_volume
                    cond3 = vol > (vol_ma5 * vol_ratio)
                    cond4 = (rsi >= rsi_min) and (rsi <= rsi_max)
                    cond5 = close >= (high60 * 0.95)
                    
                    if cond1 and cond2 and cond3 and cond4 and cond5:
                        stock_id = ticker.replace(".TW", "")
                        
                        # ★ 計算勝率 (只有入選的才算，節省時間)
                        win_rate_10pct = calculate_win_rate(df)
                        
                        results.append({
                            "代號": stock_id,
                            "名稱": stock_map.get(stock_id, stock_id),
                            "收盤價": round(close, 2),
                            "RSI": round(rsi, 1),
                            "爆量倍數": round(vol/vol_ma5, 1) if vol_ma5 > 0 else 0,
                            "🎯10日勝率%": win_rate_10pct  # 新增欄位
                        })
                except:
                    continue
    
    progress_bar.empty()
    status_text.empty()
    
    if results:
        res_df = pd.DataFrame(results)
        
        # 把 N/A 的勝率換成 -1 方便排序，顯示時再換回來
        res_df['sort_win'] = pd.to_numeric(res_df['🎯10日勝率%'], errors='coerce').fillna(-1)
        res_df = res_df.sort_values(by="sort_win", ascending=False).drop(columns=['sort_win'])
        
        st.success(f"掃描完成！共發現 {len(res_df)} 檔潛力股")
        st.dataframe(res_df, use_container_width=True)
        
        # 存檔
        csv = res_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載含勝率報表 CSV",
            data=csv,
            file_name=f"sniper_winrate_{datetime.now().strftime('%Y%m%d')}.csv",
            mime='text/csv',
        )
        
        st.markdown("---")
        st.subheader("📊 個股 K 線圖檢視")
        selected_stock = st.selectbox("請選擇股票：", res_df['代號'] + " " + res_df['名稱'])
        
        if selected_stock:
            stock_code = selected_stock.split(" ")[0]
            st.write(f"正在載入 {stock_code} 圖表...")
            chart_data = yf.download(f"{stock_code}.TW", period="6mo", interval="1d", progress=False)
            if isinstance(chart_data.columns, pd.MultiIndex):
                chart_data.columns = chart_data.columns.get_level_values(0)
            
            chart_data['MA20'] = chart_data['Close'].rolling(window=20).mean()
            chart_data['MA60'] = chart_data['Close'].rolling(window=60).mean()
            
            fig
