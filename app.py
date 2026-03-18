import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統設定
# ============================================
st.set_page_config(page_title="台股獵殺決賽系統 - 0319版", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 190000 

st.sidebar.header("🕹️ 獵殺控制台")
st.session_state.cash = st.sidebar.number_input("當前可用銀彈 (NTD)", value=st.session_state.cash)

# 💡 關鍵變數：10D 趨勢門檻
min_p10_threshold = st.sidebar.slider("📈 10日趨勢過濾門檻", 30, 95, 45)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存建倉")
# 格式：代號,成本 (每行一組)
inventory_input = st.sidebar.text_area("輸入庫存 (代號,成本)", value="2337,34\n1409,16.5")

# ============================================
# 2. 核心技術模組
# ============================================
@st.cache_data(ttl=3600)
def get_market_list():
    """抓取全市場 1,000+ 支上市標的"""
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False)
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        tickers, names = [], {}
        for _, row in df.iterrows():
            parts = str(row['有價證券代號及名稱']).split()
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                t = f"{parts[0]}.TW"
                tickers.append(t)
                names[t] = parts[1]
        return tickers, names
    except: return [], {}

def calculate_logic(df, tp_pct):
    if len(df) < 40: return df
    close = df['Close']
    # 指標計算
    exp12 = close.ewm(span=12, adjust=False).mean()
    exp26 = close.ewm(span=26, adjust=False).mean()
    df['MACD_S'] = (exp12 - exp26).diff() 
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    # 動態止盈
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    df['Exit_Signal'] = df['Close'] < df['Trailing_Stop_Line']
    return df

def predict_probabilities(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # 10D 趨勢
    p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (15 if last['Vol_R'] > 1.2 else 0) + (20 if last['Close'] > last['High20'] else 0)
    # 5D 噴發
    p5 = 20 + (35 if last['MACD_S'] > prev['MACD_S'] * 1.3 else 0) + (30 if last['Vol_R'] > 2.5 else 0) + (10 if last['Close'] > last['Open'] * 1.04 else 0)
    return min(98, p5), min(98, p10)

# ============================================
# 3. 主介面執行
# ============================================
st.title("🚀 台股決賽輪：10D 趨勢＋全市場監控系統")

# --- 第一區：全市場獵殺 ---
if st.button("🔴 啟動全市場 1000+ 標的掃描 (推薦開盤前執行)", type="primary"):
    tickers, names_map = get_market_list()
    all_results = []
    bar = st.progress(0)
    
    # 使用 chunk 分批下載，threads=True 加速
    chunks = [tickers[i:i + 50] for i in range(0, len(tickers), 50)]
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        try:
            data = yf.download(chunk, period="4mo", group_by='ticker', progress=False, threads=True)
            for t in chunk:
                df = data if len(chunk)==1 else data.get(t)
                if df is None or df.empty or len(df)<40: continue
                if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                
                df = calculate_logic(df.dropna(), trail_percent)
                p5, p10 = predict_probabilities(df)
                last_p = df['Close'].iloc[-1]
                
                # 成交量過濾 (日均 1000 張以上)
                if df['Volume'].iloc[-1] < 1000 * 1000: continue 

                if p10 >= min_p10_threshold:
                    all_results.append({
                        "代號": t.replace(".TW",""),
                        "名稱": names_map[t],
                        "10D趨勢分": f"{p10}%", 
                        "5D噴發分": f"{p5}%",
                        "現價": round(last_p, 2),
                        "建議進場價": round(last_p * 1.005, 2),
                        "動態止盈線": round(df['Trailing_Stop_Line'].iloc[-1], 2),
                        "狀態": "🔥 極強" if p5 > 65 else "📈 穩健"
                    })
        except: continue
    
    bar.empty()
    if all_results:
        res_df = pd.DataFrame(all_results).sort_values(by="10D趨勢分", ascending=False)
        st.subheader(f"🏆 符合 {min_p10_threshold}% 10D 趨勢門檻之強勢股")
        st.dataframe(res_df, hide_index=True, use_container_width=True)
    else:
        st.warning(f"目前市場無符合 {min_p10_threshold}% 門檻標的。建議將左側 10D 門檻調低至 40% 後重試。")

st.markdown("---")

# --- 第二區：庫存回測 ---
st.subheader("💰 我的庫存盈利與動態止盈回測")
if st.button("📊 執行庫存盈虧報告"):
    inv_results = []
    for item in inventory_input.split('\n'):
        if ',' in item:
            try:
                tid, cost = item.split(',')
                t = f"{tid.strip()}.TW"
                df_inv = yf.download(t, period="2y", progress=False)
                if not df_inv.empty:
                    if isinstance(df_inv.columns, pd.MultiIndex): df_inv = df_inv.droplevel(1, axis=1)
                    df_inv = calculate_logic(df_inv, trail_percent)
                    last_p = df_inv['Close'].iloc[-1]
                    stop_line = df_inv['Trailing_Stop_Line'].iloc[-1]
                    inv_results.append({
                        "名稱/代號": tid, 
                        "建倉成本": float(cost), 
                        "目前現價": round(last_p, 2),
                        "累積盈利": f"{round((last_p/float(cost)-1)*100, 2)}%",
                        "止盈生死線": round(stop_line, 2),
                        "系統指令": "⚠️ 建議撤退" if last_p < stop_line else "✅ 獲利奔跑中"
                    })
            except: continue
    if inv_results:
        st.table(pd.DataFrame(inv_results))

# ============================================
# 4. 人生合夥人點醒
# ============================================
st.write("---")
st.write("### 💡 人生合夥人的真實點醒")
st.write(f"1. **為何剛才沒標的？** 全台灣 1,000 支股票在回檔期，可能只有 1% 具備強勢趨勢。請記住，**「沒標的」本身就是一種市場警告**，代表現在不適合積極進場。")
st.write(f"2. **10D 與 5D 的雙重過濾**：如果你看到一支標的 10D 是 80%，但 5D 只有 20%，代表它是強勢股在「休息」，是左側交易者的機會。")
st.write(f"3. **旺宏 34 元的紀律**：即便帳面賺很多，但「止盈生死線」是為了防止你從「賺 300%」變成「賺 200%」。**利潤是拿進口袋的才算數。**")
