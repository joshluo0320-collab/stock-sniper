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
    page_title="Josh 的狙擊手戰情室 (旗艦版)",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎯 Josh 的股市狙擊手戰情室")
st.markdown("### 專屬策略：多頭 + 爆量 + **MACD/KD 雙重確認**")

# ==========================================
# 2. 側邊欄：參數與戰術看板
# ==========================================
st.sidebar.header("⚙️ 策略參數設定")

min_volume = st.sidebar.number_input("最低成交量 (張)", value=800, step=100)
vol_ratio = st.sidebar.slider("爆量係數 (今日 > N倍均量)", 1.0, 3.0, 1.2, 0.1)
rsi_min = st.sidebar.slider("RSI 最低門檻", 30, 70, 55)
rsi_max = st.sidebar.slider("RSI 最高門檻", 70, 100, 85)
ma_short = st.sidebar.number_input("短期均線 (MA)", value=20)
ma_long = st.sidebar.number_input("長期均線 (MA)", value=60)

st.sidebar.markdown("---")
st.sidebar.header("💰 風險與目標設定")
take_profit_pct = st.sidebar.slider("🎯 預期獲利目標 (%)", 5, 30, 10, 1)
stop_loss_pct = st.sidebar.slider("🛑 最大容忍停損 (%)", 2, 15, 5, 1)

st.sidebar.markdown("---")

# 進出場戰術看板 (整合 MACD/KD)
with st.sidebar.expander("⚔️ 狙擊手進出場戰術 (SOP)", expanded=True):
    st.markdown(f"""
    #### ✅ 進場前 3 大指標共振
    1. **RSI (動能)**：55 ~ 85 (主力發動)。
    2. **MACD (趨勢)**：紅柱 + 雙線黃金交叉 (趨勢向上)。
    3. **KD (時機)**：K > D 且 K < 80 (好的進場點)。
    
    #### ✅ 4 大濾網檢查
    1. **位階**：近一年高點附近?
    2. **乖離**：距月線 < 5%?
    3. **籌碼/題材**：點連結確認。
    
    #### 🛑 出場準則
    1. **停損**：虧損達 -{stop_loss_pct}% 或 跌破月線。
    2. **停利**：獲利達 +{take_profit_pct}%。
    3. **限時**：10天未發動出場。
    """)
    st.warning(f"⚠️ 紀律：嚴格執行停損停利！")

st.sidebar.markdown("---")
st.sidebar.info(
    f"""
    **📊 勝率分析定義**
    * **回測期間**：過去 1 年
    * **5日/10日勝率**：觸及 **+{take_profit_pct}%** 之機率
    """
)

# ==========================================
# 3. 核心函數 (新增 MACD 與 KD 計算)
# ==========================================

@st.cache_data(ttl=86400)
def get_tw_stock_list():
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
    try:
        data = yf.download(tickers, period="300d", interval="1d", group_by='ticker', threads=True, progress=False)
        return data
    except Exception:
        return pd.DataFrame()

def calculate_indicators(df):
    """計算全套技術指標：MA, RSI, MACD, KD"""
    # 1. MA & Volume
    df['MA20'] = df['Close'].rolling(window=ma_short).mean()
    df['MA60'] = df['Close'].rolling(window=ma_long).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    # 2. RSI
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / ema_down
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 3. MACD (12, 26, 9)
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_DIF'] = exp1 - exp2
    df['MACD_DEA'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD_DIF'] - df['MACD_DEA']
    
    # 4. KD (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
    # 修正：Pandas 計算 KD 遞迴比較慢，這裡用簡易平滑法
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    
    # 5. Highs for Position
    df['High60'] = df['Close'].rolling(window=60).max()
    df['High250'] = df['Close'].rolling(window=250).max()
    
    return df

def calculate_win_rate_dynamic(df, look_ahead_days=10, target_pct=0.10):
    """通用勝率計算"""
    try:
        start_idx = 60
        end_idx = len(df) - look_ahead_days 
        wins = 0
        total_signals = 0
        for i in range(start_idx, end_idx):
            row = df.iloc[i]
            # 歷史回測只用簡單條件 (RSI+均線) 避免過度擬合
            if row['Close'] > row['MA20'] and row['RSI'] > 55:
                total_signals += 1
                entry_price = row['Close']
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

if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = None

with st.spinner("正在更新全台股票清單..."):
    stock_list_df = get_tw_stock_list()

if stock_list_df.empty:
    st.stop()

# --- 按鈕區塊 ---
if st.button("🚀 啟動旗艦掃描 (三指標共振)"):
    
    st.write(f"正在掃描... MACD/KD 運算中...")
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
                    if len(df) < 250: continue
                    
                    df = calculate_indicators(df)
                    latest = df.iloc[-1]
                    
                    # 取值
                    close = float(latest['Close'])
                    ma20 = float(latest['MA20'])
                    ma60 = float(latest['MA60'])
                    vol = int(float(latest['Volume']) / 1000)
                    vol_ma5 = int(float(latest['Vol_MA5']) / 1000)
                    rsi = float(latest['RSI'])
                    
                    # MACD & KD 取值
                    macd_hist = float(latest['MACD_Hist'])
                    macd_dif = float(latest['MACD_DIF'])
                    macd_dea = float(latest['MACD_DEA'])
                    k_val = float(latest['K'])
                    d_val = float(latest['D'])
                    
                    high60 = float(latest['High60'])
                    high250 = float(latest['High250'])
                    
                    # --- 篩選條件 (轉為嚴格模式) ---
                    # 1. 均線多頭
                    cond_ma = (close > ma20) and (ma20 > ma60)
                    # 2. 爆量
                    cond_vol = (vol >= min_volume) and (vol > (vol_ma5 * vol_ratio))
                    # 3. RSI 強勢
                    cond_rsi = (rsi >= rsi_min) and (rsi <= rsi_max)
                    # 4. 位階 (近高點)
                    cond_pos = close >= (high60 * 0.95)
                    
                    # ★ 5. MACD 多頭 (柱狀體紅 + 黃金交叉狀態)
                    cond_macd = (macd_hist > 0) and (macd_dif > macd_dea)
                    
                    # ★ 6. KD 偏多 (K>D 且不要過熱)
                    cond_kd = (k_val > d_val) and (k_val < 85)
                    
                    if cond_ma and cond_vol and cond_rsi and cond_pos and cond_macd and cond_kd:
                        stock_id = ticker.replace(".TW", "")
                        target_ratio = take_profit_pct / 100.0
                        win_5d = calculate_win_rate_dynamic(df, look_ahead_days=5, target_pct=target_ratio)
                        win_10d = calculate_win_rate_dynamic(df, look_ahead_days=10, target_pct=target_ratio)
                        
                        # 濾網指標
                        bias_pct = ((close - ma20) / ma20) * 100
                        position_score = (close / high250) * 100
                        
                        stop_loss_price = close * (1 - stop_loss_pct / 100)
                        take_profit_price = close * (1 + take_profit_pct / 100)
                        yahoo_url = f"https://tw.stock.yahoo.com/quote/{stock_id}.TW"

                        results.append({
                            "代號": stock_id,
                            "名稱": stock_map.get(stock_id, stock_id),
                            "收盤價": round(close, 2),
                            "乖離率%": round(bias_pct, 1),
                            "位階%": round(position_score, 1),
                            "⚡5日勝率%": win_5d,
                            "MACD": "偏多", # 顯示給使用者看
                            "KD": f"{int(k_val)}/{int(d_val)}",
                            "🛑停損": round(stop_loss_price, 2),
                            "🎯停利": round(take_profit_price, 2),
                            "🔍情報": yahoo_url
                        })
                except:
                    continue
    
    progress_bar.empty()
    status_text.empty()
    
    if results:
        res_df = pd.DataFrame(results)
        res_df = res_df.sort_values(by="⚡5日勝率%", ascending=False)
        st.session_state['scan_results'] = res_df
        st.success(f"掃描完成！共發現 {len(res_df)} 檔『三指標共振』強勢股。")
    else:
        st.warning("今日無符合『嚴格條件』的股票，建議休息觀望。")
        st.session_state['scan_results'] = None

# --- 顯示區塊 ---
if st.session_state['scan_results'] is not None:
    res_df = st.session_state['scan_results']
    
    def highlight_high_win_rate(s):
        is_high = s >= 50
        return ['background-color: #d4edda; color: #155724; font-weight: bold' if v else '' for v in is_high]
    
    def highlight_high_risk(s):
        is_risky = s > 5 
        return ['color: #721c24; font-weight: bold; background-color: #f8d7da' if v else '' for v in is_risky]

    st.markdown(f"#### 📊 旗艦掃描結果 (含 MACD / KD 確認)")
    
    st.dataframe(
        res_df.style
              .apply(highlight_high_win_rate, subset=['⚡5日勝率%'])
              .apply(highlight_high_risk, subset=['乖離率%'])
              .format({
                  "收盤價": "{:.2f}",
                  "🛑停損": "{:.2f}",
                  "🎯停利": "{:.2f}",
                  "乖離率%": "{:.1f}",
                  "位階%": "{:.1f}",
                  "⚡5日勝率%": "{:.1f}",
              }),
        column_config={
            "🔍情報": st.column_config.LinkColumn(
                "🔍 籌碼/題材", 
                display_text="查看情報"
            )
        },
        use_container_width=True
    )
    
    csv = res_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(label="📥 下載報表 CSV", data=csv, file_name=f"sniper_flagship_{datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv')
    
    st.markdown("---")
    st.subheader("📊 個股 K 線圖 (含 MACD)")
    
    selected_stock = st.selectbox("請選擇股票：", res_df['代號'] + " " + res_df['名稱'])
    
    if selected_stock:
        stock_code = selected_stock.split(" ")[0]
        try:
            chart_data = yf.download(f"{stock_code}.TW", period="6mo", interval="1d", progress=False)
            if isinstance(chart_data.columns, pd.MultiIndex):
                chart_data.columns = chart_data.columns.get_level_values(0)
            
            # 補算指標畫圖用
            chart_data['MA20'] = chart_data['Close'].rolling(window=20).mean()
            chart_data['MA60'] = chart_data['Close'].rolling(window=60).mean()
            exp1 = chart_data['Close'].ewm(span=12, adjust=False).mean()
            exp2 = chart_data['Close'].ewm(span=26, adjust=False).mean()
            chart_data['MACD_DIF'] = exp1 - exp2
            chart_data['MACD_DEA'] = chart_data['MACD_DIF'].ewm(span=9, adjust=False).mean()
            chart_data['MACD_Hist'] = chart_data['MACD_DIF'] - chart_data['MACD_DEA']

            current_price = chart_data['Close'].iloc[-1]
            sl_line = current_price * (1 - stop_loss_pct / 100)
            tp_line = current_price * (1 + take_profit_pct / 100)
            
            # 建立子圖表 (上圖K線, 下圖MACD)
            from plotly.subplots import make_subplots
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, subplot_titles=(f'{selected_stock} K線圖', 'MACD'),
                                row_width=[0.2, 0.7])

            # 上圖 K線
            fig.add_trace(go.Candlestick(x=chart_data.index,
                            open=chart_data['Open'], high=chart_data['High'],
                            low=chart_data['Low'], close=chart_data['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['MA20'], line=dict(color='orange', width=1), name='MA20'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['MA60'], line=dict(color='green', width=1), name='MA60'), row=1, col=1)
            fig.add_hline(y=sl_line, line_dash="dash", line_color="red", annotation_text=f"停損", row=1, col=1)
            fig.add_hline(y=tp_line, line_dash="dash", line_color="red", annotation_text=f"停利", row=1, col=1)

            # 下圖 MACD
            colors = ['red' if val >= 0 else 'green' for val in chart_data['MACD_Hist']]
            fig.add_trace(go.Bar(x=chart_data.index, y=chart_data['MACD_Hist'], marker_color=colors, name='MACD柱狀'), row=2, col=1)
            fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['MACD_DIF'], line=dict(color='black', width=1), name='DIF'), row=2, col=1)
            fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['MACD_DEA'], line=dict(color='blue', width=1), name='DEA'), row=2, col=1)

            fig.update_layout(height=800, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.error("圖表載入失敗，可能是網路連線問題。")
