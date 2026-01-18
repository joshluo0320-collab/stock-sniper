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
    page_title="Josh 的狙擊手戰情室 (全連動版)",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎯 Josh 的股市狙擊手戰情室")
st.markdown("### 專屬策略：多頭排列 + 爆量 + **動態勝率連動**")

# ==========================================
# 2. 側邊欄：參數與戰術看板
# ==========================================
st.sidebar.header("⚙️ 策略參數設定")

min_volume = st.sidebar.number_input("最低成交量 (張)", value=800, step=100)
vol_ratio = st.sidebar.slider("爆量係數 (今日 > N倍均量)", 1.0, 3.0, 1.2, 0.1)
rsi_min = st.sidebar.slider("RSI 最低門檻", 30, 70, 55)
rsi_max = st.sidebar.slider("RSI 最高門檻 (避免過熱)", 70, 100, 85)
ma_short = st.sidebar.number_input("短期均線 (MA)", value=20)
ma_long = st.sidebar.number_input("長期均線 (MA)", value=60)

st.sidebar.markdown("---")
st.sidebar.header("💰 風險與目標設定 (連動勝率)")
# 這裡設定的 % 數，現在會直接影響勝率計算！
take_profit_pct = st.sidebar.slider("🎯 預期獲利目標 (%)", 5, 30, 10, 1)
stop_loss_pct = st.sidebar.slider("🛑 最大容忍停損 (%)", 2, 15, 5, 1)

st.sidebar.markdown("---")

# 進出場戰術看板
with st.sidebar.expander("⚔️ 狙擊手進出場戰術 (SOP)", expanded=True):
    st.markdown(f"""
    #### ✅ 進場檢查 (Entry)
    1. **趨勢**：多頭排列 (股價 > 月 > 季)。
    2. **動能**：RSI 在 55~85。
    3. **籌碼**：爆量 > 1.2倍均量。
    
    #### 🛑 出場準則 (Exit)
    1. **停損 (防守)**：
       - **虧損達 -{stop_loss_pct}%** ➜ **強制離場**。
       - 或 **跌破月線**。
    2. **停利 (進攻)**：
       - **獲利達 +{take_profit_pct}%** ➜ 分批獲利。
       - 或 **RSI > 85** (過熱)。
    """)
    st.warning(f"⚠️ 紀律：虧損不可超過 {stop_loss_pct}%！")

st.sidebar.markdown("---")
st.sidebar.info(
    f"""
    **📊 動態勝率定義 (隨滑桿變動)**
    * **回測期間**：過去 1 年
    * **5日勝率**：5天內是否觸及 **+{take_profit_pct}%**
    * **10日勝率**：10天內是否觸及 **+{take_profit_pct}%**
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
    """下載數據"""
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

def calculate_win_rate_dynamic(df, look_ahead_days=10, target_pct=0.10):
    """
    通用勝率計算函數
    target_pct 會接收外部傳入的參數 (例如 0.20 代表 20%)
    """
    try:
        start_idx = 60
        end_idx = len(df) - look_ahead_days 
        wins = 0
        total_signals = 0
        
        for i in range(start_idx, end_idx):
            row = df.iloc[i]
            if row['Close'] > row['MA20'] and row['RSI'] > 55:
                total_signals += 1
                entry_price = row['Close']
                # 這裡使用動態傳入的 target_pct
                target_price = entry_price * (1 + target_pct)
                future_days = df.iloc[i+1 : i+1 + look_ahead_days]
                max_price = future_days['High'].max()
                if max_price >= target_price:
                    wins += 1
        
        if total_signals == 0: return 0.0 
        win_rate = (wins / total_signals) * 100
        return round(win_rate, 2)
    except Exception:
        return 0.0

# ==========================================
# 4. 主程式邏輯
# ==========================================

# 初始化 session_state
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = None

with st.spinner("正在更新全台股票清單..."):
    stock_list_df = get_tw_stock_list()

if stock_list_df.empty:
    st.stop()

# --- 按鈕區塊 ---
if st.button("🚀 啟動雙重勝率掃描"):
    
    st.write(f"正在計算... 目標：{take_profit_pct}% 獲利機率")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    stock_map = dict(zip(stock_list_df['代號'], stock_list_df['名稱']))
    tickers = [f"{x}.TW" for x in stock_list_df['代號'].tolist()]
    
    chunk_size = 30
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
                    if len(df) < 100: continue
                    
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
                    
                    # 篩選條件
                    cond1 = (close > ma20) and (ma20 > ma60)
                    cond2 = vol >= min_volume
                    cond3 = vol > (vol_ma5 * vol_ratio)
                    cond4 = (rsi >= rsi_min) and (rsi <= rsi_max)
                    cond5 = close >= (high60 * 0.95)
                    
                    if cond1 and cond2 and cond3 and cond4 and cond5:
                        stock_id = ticker.replace(".TW", "")
                        
                        # ★★★ 關鍵修改：將滑桿的 % 數除以 100 傳入 ★★★
                        target_ratio = take_profit_pct / 100.0
                        
                        win_5d = calculate_win_rate_dynamic(df, look_ahead_days=5, target_pct=target_ratio)
                        win_10d = calculate_win_rate_dynamic(df, look_ahead_days=10, target_pct=target_ratio)
                        
                        # 計算停損停利價
                        stop_loss_price = close * (1 - stop_loss_pct / 100)
                        take_profit_price = close * (1 + take_profit_pct / 100)

                        results.append({
                            "代號": stock_id,
                            "名稱": stock_map.get(stock_id, stock_id),
                            "收盤價": round(close, 2),
                            "🛑停損價": round(stop_loss_price, 2),
                            "🎯停利價": round(take_profit_price, 2),
                            "RSI": round(rsi, 2),
                            "爆量倍數": round(vol/vol_ma5, 2) if vol_ma5 > 0 else 0,
                            "⚡5日勝率%": win_5d,
                            "🎯10日勝率%": win_10d
                        })
                except:
                    continue
    
    progress_bar.empty()
    status_text.empty()
    
    if results:
        res_df = pd.DataFrame(results)
        res_df = res_df.sort_values(by="⚡5日勝率%", ascending=False)
        st.session_state['scan_results'] = res_df
        st.success(f"掃描完成！依據目標 {take_profit_pct}% 計算勝率")
    else:
        st.warning("今日無符合條件的股票。")
        st.session_state['scan_results'] = None

# --- 顯示區塊 ---
if st.session_state['scan_results'] is not None:
    res_df = st.session_state['scan_results']
    
    def highlight_high_win_rate(s):
        is_high = s >= 50
        return ['background-color: #d4edda; color: #155724; font-weight: bold' if v else '' for v in is_high]

    # 標題現在會顯示動態的 % 數
    st.markdown(f"#### 📊 掃描結果 (目標獲利：**{take_profit_pct}%** 的達成率)")
    
    st.dataframe(
        res_df.style.apply(highlight_high_win_rate, subset=['⚡5日勝率%', '🎯10日勝率%'])
              .format({
                  "收盤價": "{:.2f}",
                  "🛑停損價": "{:.2f}",
                  "🎯停利價": "{:.2f}",
                  "RSI": "{:.2f}",
                  "爆量倍數": "{:.2f}",
                  "⚡5日勝率%": "{:.2f}",
                  "🎯10日勝率%": "{:.2f}"
              }),
        use_container_width=True
    )
    
    csv = res_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下載報表 (含停損停利價) CSV",
        data=csv,
        file_name=f"sniper_report_{datetime.now().strftime('%Y%m%d')}.csv",
        mime='text/csv',
    )
    
    st.markdown("---")
    st.subheader("📊 個股 K 線圖檢視")
    
    selected_stock = st.selectbox("請選擇股票：", res_df['代號'] + " " + res_df['名稱'])
    
    if selected_stock:
        stock_code = selected_stock.split(" ")[0]
        try:
            chart_data = yf.download(f"{stock_code}.TW", period="6mo", interval="1d", progress=False)
            if isinstance(chart_data.columns, pd.MultiIndex):
                chart_data.columns = chart_data.columns.get_level_values(0)
            
            chart_data['MA20'] = chart_data['Close'].rolling(window=20).mean()
            chart_data['MA60'] = chart_data['Close'].rolling(window=60).mean()
            
            current_price = chart_data['Close'].iloc[-1]
            sl_line = current_price * (1 - stop_loss_pct / 100)
            tp_line = current_price * (1 + take_profit_pct / 100)
            
            fig = go.Figure(data=[go.Candlestick(x=chart_data.index,
                            open=chart_data['Open'], high=chart_data['High'],
                            low=chart_data['Low'], close=chart_data['Close'], name='K線')])
            
            fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['MA20'], line=dict(color='orange', width=1), name='MA20'))
            fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['MA60'], line=dict(color='green', width=1), name='MA60'))
            
            fig.add_hline(y=sl_line, line_dash="dash", line_color="red", annotation_text=f"停損 (-{stop_loss_pct}%)")
            fig.add_hline(y=tp_line, line_dash="dash", line_color="red", annotation_text=f"停利 (+{take_profit_pct}%)")
            
            fig.update_layout(title=f"{selected_stock} 日線圖 (含風險規劃)", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.error("圖表載入失敗，可能是網路連線問題。")
