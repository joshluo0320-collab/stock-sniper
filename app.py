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
    page_title="Josh 的狙擊手戰情室 (庫存管理版)",
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
# 2. 側邊欄：參數設定
# ==========================================
st.sidebar.header("⚙️ 掃描參數設定")
strict_mode = st.sidebar.checkbox("🔒 開啟嚴格篩選 (Strict Mode)", value=False)
min_volume = st.sidebar.number_input("最低成交量", value=800, step=100)
vol_ratio = st.sidebar.slider("爆量係數", 1.0, 3.0, 1.2, 0.1)
ma_short = st.sidebar.number_input("短期均線 (MA)", value=20)
ma_long = st.sidebar.number_input("長期均線 (MA)", value=60)

st.sidebar.markdown("---")
st.sidebar.header("💰 庫存管理操作")

# 新增庫存區塊
with st.sidebar.form("add_stock_form"):
    st.write("📥 新增持股紀錄")
    new_stock_id = st.text_input("股票代號 (如 2330)")
    new_stock_price = st.number_input("買入成本", min_value=0.0, step=0.1)
    new_stock_qty = st.number_input("股數 (張數*1000)", min_value=1000, step=1000, value=1000)
    submitted = st.form_submit_button("💾 加入庫存")
    
    if submitted and new_stock_id and new_stock_price > 0:
        try:
            # 簡單抓取名稱
            stock_info = yf.Ticker(f"{new_stock_id}.TW")
            # 這裡簡單處理，實際名稱可能需要 mapping，先用代號代替
            new_name = new_stock_id 
            
            df_curr = pd.read_csv(PORTFOLIO_FILE)
            new_row = pd.DataFrame({
                '代號': [new_stock_id], 
                '名稱': [new_name], 
                '成本價': [new_stock_price], 
                '股數': [new_stock_qty],
                '買入日期': [datetime.now().strftime("%Y-%m-%d")]
            })
            df_curr = pd.concat([df_curr, new_row], ignore_index=True)
            df_curr.to_csv(PORTFOLIO_FILE, index=False)
            st.success(f"已加入 {new_stock_id}！請切換至『我的庫存』查看。")
        except Exception as e:
            st.error(f"新增失敗: {e}")

if st.sidebar.button("🗑️ 清空所有庫存"):
    df_init = pd.DataFrame(columns=['代號', '名稱', '成本價', '股數', '買入日期'])
    df_init.to_csv(PORTFOLIO_FILE, index=False)
    st.warning("庫存已清空！")

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
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rs = up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + rs))
    
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Hist'] = (exp1 - exp2) - (exp1 - exp2).ewm(span=9, adjust=False).mean()
    
    df['RSV'] = (df['Close'] - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    
    return df

def calculate_win_rate(df, days=10, target=0.1):
    try:
        wins = 0
        total = 0
        for i in range(60, len(df)-days):
            if df.iloc[i]['Close'] > df.iloc[i]['MA20'] and df.iloc[i]['RSI'] > 55:
                total += 1
                if df.iloc[i+1:i+1+days]['High'].max() >= df.iloc[i]['Close'] * (1+target):
                    wins += 1
        return round((wins/total)*100, 1) if total > 0 else 0
    except: return 0

# ==========================================
# 4. 主介面：分頁系統
# ==========================================
tab1, tab2 = st.tabs(["🚀 戰略掃描 (找股票)", "📁 我的庫存戰情 (顧股票)"])

# --- 分頁 1: 掃描功能 (維持原樣) ---
with tab1:
    if st.button("🚀 啟動掃描"):
        with st.spinner("掃描運算中..."):
            stock_list = get_tw_stock_list()
            if not stock_list.empty:
                tickers = [f"{x}.TW" for x in stock_list['代號'].tolist()]
                # 為了示範速度，這裡只取前 200 檔模擬，實際使用請移除切片
                data = get_stock_data(tickers) 
                
                results = []
                if not data.empty:
                    for ticker in tickers:
                        try:
                            if ticker not in data.columns.levels[0]: continue
                            df = data[ticker].copy().dropna()
                            if len(df) < 250: continue
                            
                            df = calculate_indicators(df)
                            curr = df.iloc[-1]
                            
                            # 篩選邏輯
                            if not (curr['Close'] > curr['MA20'] > curr['MA60']): continue
                            if not (curr['Volume'] >= min_volume and curr['Volume'] > curr['Vol_MA5'] * vol_ratio): continue
                            if not (55 <= curr['RSI'] <= 85): continue
                            if curr['MACD_Hist'] <= 0: continue
                            
                            win10 = calculate_win_rate(df)
                            if win10 < (50 if strict_mode else 40): continue
                            
                            bias = (curr['Close'] - curr['MA20']) / curr['MA20'] * 100
                            if strict_mode and bias > 10: continue

                            # 評估邏輯
                            assess = "🟢安全" if bias <= 5 else ("🟡拉回" if bias <= 10 else ("🔥妖股" if win10 >= 60 else "🔴風險"))
                            
                            results.append({
                                "代號": ticker.replace(".TW", ""),
                                "名稱": stock_list[stock_list['代號']==ticker.replace(".TW", "")]['名稱'].values[0],
                                "評估": assess,
                                "10日勝率%": win10,
                                "收盤": round(curr['Close'], 2),
                                "乖離%": round(bias, 1)
                            })
                        except: continue
                
                if results:
                    st.dataframe(pd.DataFrame(results).sort_values("10日勝率%", ascending=False), use_container_width=True)
                else:
                    st.warning("無符合條件股票")

# --- 分頁 2: 庫存管理 (妖股續抱核心) ---
with tab2:
    st.markdown("### 📁 庫存戰術看板：移動停利監控")
    st.info("💡 **妖股戰術**：獲利 > 10% 後，請觀察 **MA10 (10日線)**。只要沒跌破，就一直抱著，直到跌破再賣。")
    
    if os.path.exists(PORTFOLIO_FILE):
        df_p = pd.read_csv(PORTFOLIO_FILE)
        
        if not df_p.empty:
            # 抓取庫存最新價格
            tickers_p = [f"{x}.TW" for x in df_p['代號'].astype(str).tolist()]
            data_p = get_stock_data(tickers_p)
            
            p_results = []
            total_profit = 0
            
            for index, row in df_p.iterrows():
                try:
                    ticker = f"{str(row['代號'])}.TW"
                    if ticker in data_p.columns.levels[0]:
                        df = data_p[ticker].copy().dropna()
                        df = calculate_indicators(df)
                        curr = df.iloc[-1]
                        
                        curr_price = curr['Close']
                        cost = row['成本價']
                        qty = row['股數']
                        profit_pct = ((curr_price - cost) / cost) * 100
                        profit_abs = (curr_price - cost) * qty
                        total_profit += profit_abs
                        
                        # ★★★ 戰術建議核心邏輯 ★★★
                        ma5 = curr['MA5']
                        ma10 = curr['MA10']
                        
                        action = ""
                        color = ""
                        
                        if profit_pct < -5:
                            action = "🛑 停損 (虧損擴大)"
                        elif profit_pct < 10:
                            action = "🛌 續抱 (等待發動)"
                        elif profit_pct >= 10:
                            # 獲利超過 10%，進入妖股模式
                            if curr_price < ma10:
                                action = "💰 獲利了結 (跌破10日線)"
                            elif curr_price < ma5:
                                action = "⚠️ 警戒 (跌破5日線，可減碼)"
                            else:
                                action = "🚀 妖股續抱 (守住均線)"
                        
                        p_results.append({
                            "代號": row['代號'],
                            "名稱": row['名稱'],
                            "現價": round(curr_price, 2),
                            "成本": cost,
                            "獲利%": round(profit_pct, 1),
                            "帳面損益": int(profit_abs),
                            "MA5支撐": round(ma5, 2),
                            "MA10支撐": round(ma10, 2),
                            "🤖 戰術建議": action
                        })
                except Exception as e:
                    continue
            
            if p_results:
                st.metric("💰 總帳面損益", f"{int(total_profit):,} 元", delta_color="normal")
                
                df_res = pd.DataFrame(p_results)
                
                # 樣式設定
                def highlight_action(val):
                    if "妖股" in val: return 'background-color: #d4edda; color: green; font-weight: bold'
                    if "獲利" in val: return 'background-color: #fff3cd; color: #856404; font-weight: bold'
                    if "停損" in val: return 'background-color: #f8d7da; color: red; font-weight: bold'
                    return ''

                st.dataframe(
                    df_res.style.applymap(highlight_action, subset=['🤖 戰術建議'])
                          .format({"現價": "{:.2f}", "獲利%": "{:.1f}%", "帳面損益": "{:,}", "MA5支撐": "{:.2f}"}),
                    use_container_width=True
                )
            else:
                st.warning("無法讀取庫存最新股價")
        else:
            st.info("尚無庫存，請從左側新增。")
