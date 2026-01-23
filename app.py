import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import plotly.graph_objects as go
from datetime import datetime, timedelta
import urllib3
from plotly.subplots import make_subplots
import os

# 忽略 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. 頁面設定與初始化
# ==========================================
st.set_page_config(
    page_title="Josh 的狙擊手戰情室 (全功能指揮官版)",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化庫存檔案
PORTFOLIO_FILE = 'my_portfolio.csv'
if not os.path.exists(PORTFOLIO_FILE):
    df_init = pd.DataFrame(columns=['代號', '名稱', '成本價', '股數', '買入日期'])
    df_init.to_csv(PORTFOLIO_FILE, index=False)

st.title("🎯 Josh 的股市狙擊手戰情室")

# ==========================================
# 2. 側邊欄：參數與庫存操作
# ==========================================
st.sidebar.header("⚙️ 掃描參數")
strict_mode = st.sidebar.checkbox("🔒 開啟嚴格篩選 (Strict)", value=False, help="勾選後：只顯示勝率>50%且不過熱的股票。")
min_volume = st.sidebar.number_input("最低成交量", value=800, step=100)
vol_ratio = st.sidebar.slider("爆量係數", 1.0, 3.0, 1.2, 0.1)

st.sidebar.markdown("---")
st.sidebar.header("💰 庫存管理")

# 新增庫存區塊
with st.sidebar.form("add_stock_form"):
    st.write("📥 新增持股")
    new_stock_id = st.text_input("股票代號 (如 2330)")
    new_stock_price = st.number_input("買入成本", min_value=0.0, step=0.1)
    new_stock_qty = st.number_input("股數", min_value=1, step=1, value=1000, help="一張請填1000，零股請填實際股數")
    submitted = st.form_submit_button("💾 加入庫存")
    
    if submitted and new_stock_id and new_stock_price > 0:
        try:
            # 讀取現有檔案
            df_curr = pd.read_csv(PORTFOLIO_FILE)
            new_row = pd.DataFrame({
                '代號': [new_stock_id], 
                '名稱': [new_stock_id], # 先暫用代號，掃描時會更新名稱
                '成本價': [new_stock_price], 
                '股數': [new_stock_qty],
                '買入日期': [datetime.now().strftime("%Y-%m-%d")]
            })
            df_curr = pd.concat([df_curr, new_row], ignore_index=True)
            df_curr.to_csv(PORTFOLIO_FILE, index=False)
            st.sidebar.success(f"已加入 {new_stock_id}！")
        except Exception as e:
            st.sidebar.error(f"失敗: {e}")

if st.sidebar.button("🗑️ 清空所有庫存"):
    df_init = pd.DataFrame(columns=['代號', '名稱', '成本價', '股數', '買入日期'])
    df_init.to_csv(PORTFOLIO_FILE, index=False)
    st.sidebar.warning("庫存已清空！")

# ==========================================
# 3. 核心函數
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
        return df[['代號', '名稱']]
    except:
        return pd.DataFrame()

def get_stock_data(tickers):
    try:
        data = yf.download(tickers, period="300d", interval="1d", group_by='ticker', threads=True, progress=False)
        return data
    except:
        return pd.DataFrame()

def calculate_indicators(df):
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rs = up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + rs))
    
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_DIF'] = exp1 - exp2
    df['MACD_DEA'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD_DIF'] - df['MACD_DEA']
    
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    
    return df

def calculate_win_rate_dynamic(df, look_ahead_days=10, target_pct=0.10):
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
                target_price = entry_price * (1 + target_pct)
                if df.iloc[i+1:i+1+look_ahead_days]['High'].max() >= target_price:
                    wins += 1
        return round((wins/total_signals)*100, 1) if total_signals > 0 else 0
    except: return 0

# ==========================================
# 4. 主介面：分頁系統
# ==========================================
tab1, tab2 = st.tabs(["🚀 戰略掃描 (找股票)", "📁 我的庫存戰情 (顧股票)"])

# --- 分頁 1: 掃描功能 ---
with tab1:
    button_text = "🚀 啟動嚴格掃描" if strict_mode else "🚀 啟動彈性掃描"
    if st.button(button_text):
        # 連線測試
        try:
            if yf.download("2330.TW", period="5d", progress=False).empty:
                st.error("❌ 連線失敗 (Yahoo API)")
                st.stop()
        except:
            st.error("❌ 連線錯誤")
            st.stop()

        st.write("正在掃描中...")
        stock_list = get_tw_stock_list()
        stock_map = dict(zip(stock_list['代號'], stock_list['名稱']))
        tickers = [f"{x}.TW" for x in stock_list['代號'].tolist()]
        
        # 這裡為了展示，實際運行建議分批
        data = get_stock_data(tickers)
        results = []
        
        if not data.empty:
            progress_bar = st.progress(0)
            total = len(tickers)
            for i, ticker in enumerate(tickers):
                if i % 50 == 0: progress_bar.progress(min((i+1)/total, 1.0))
                try:
                    # 處理 MultiIndex
                    if len(tickers) > 1:
                        if ticker not in data.columns.levels[0]: continue
                        df = data[ticker].copy()
                    else:
                        df = data.copy()
                        
                    df = df.dropna(subset=['Close'])
                    if len(df) < 250: continue
                    
                    df = calculate_indicators(df)
                    latest = df.iloc[-1]
                    
                    close = latest['Close']
                    ma20 = latest['MA20']
                    
                    # 基礎篩選
                    if not (close > ma20): continue
                    
                    win10 = calculate_win_rate_dynamic(df)
                    if win10 < 50: continue # 嚴格50%
                    
                    bias = (close - ma20) / ma20 * 100
                    if strict_mode and bias > 10: continue

                    # 評估
                    if bias <= 5: assess, entry = "🟢安全", close
                    elif bias <= 10: assess, entry = "🟡拉回", latest['MA5']
                    else: 
                        if win10 >= 60: assess, entry = "🔥妖股", close
                        else: assess, entry = "🔴風險", latest['MA10']

                    results.append({
                        "代號": ticker.replace(".TW", ""),
                        "名稱": stock_map.get(ticker.replace(".TW", ""), ticker),
                        "評估": assess,
                        "10日勝率%": win10,
                        "收盤": round(close, 2),
                        "建議價": round(entry, 2),
                        "乖離%": round(bias, 1)
                    })
                except: continue
            progress_bar.empty()
        
        if results:
            df_res = pd.DataFrame(results).sort_values("10日勝率%", ascending=False)
            st.dataframe(df_res, use_container_width=True)
        else:
            st.warning("無符合條件股票")

# --- 分頁 2: 庫存管理 ---
with tab2:
    st.markdown("### 📁 庫存戰術看板")
    if os.path.exists(PORTFOLIO_FILE):
        df_p = pd.read_csv(PORTFOLIO_FILE)
        if not df_p.empty:
            tickers_p = [f"{str(x)}.TW" for x in df_p['代號'].tolist()]
            data_p = get_stock_data(tickers_p)
            
            p_res = []
            for index, row in df_p.iterrows():
                try:
                    ticker = f"{str(row['代號'])}.TW"
                    # 處理單檔或多檔數據結構
                    if len(tickers_p) == 1:
                        df = data_p.copy()
                    else:
                        if ticker not in data_p.columns.levels[0]: continue
                        df = data_p[ticker].copy()
                        
                    df = df.dropna()
                    df = calculate_indicators(df)
                    curr = df.iloc[-1]
                    
                    # 更新名稱 (如果原本只有代號)
                    stock_name = row['名稱']
                    # 這裡可以再加強去 map 名稱，暫時用原檔
                    
                    profit = (curr['Close'] - row['成本價']) * row['股數']
                    profit_pct = (curr['Close'] - row['成本價']) / row['成本價'] * 100
                    
                    action = "🛌 續抱"
                    if profit_pct >= 10:
                        if curr['Close'] < curr['MA10']: action = "💰 獲利了結 (破MA10)"
                        elif curr['Close'] < curr['MA5']: action = "⚠️ 警戒 (破MA5)"
                        else: action = "🚀 妖股續抱"
                    elif profit_pct < -5: action = "🛑 停損"

                    p_res.append({
                        "代號": row['代號'],
                        "現價": round(curr['Close'], 2),
                        "成本": row['成本價'],
                        "獲利%": round(profit_pct, 1),
                        "損益": int(profit),
                        "MA5": round(curr['MA5'], 2),
                        "建議": action
                    })
                except: continue
            
            if p_res:
                st.dataframe(pd.DataFrame(p_res), use_container_width=True)
            else:
                st.info("無法讀取最新股價或剛新增無數據")
        else:
            st.info("目前無庫存")
