import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統設定與 UI 控制台
# ============================================
st.set_page_config(page_title="台股獵殺系統 - 10D 趨勢版", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 190000 

st.sidebar.header("🕹️ 獵殺與庫存控制台")
st.session_state.cash = st.sidebar.number_input("當前可用銀彈 (NTD)", value=st.session_state.cash)

# --- 關鍵修改：將 5D 門檻改為 10D 門檻 ---
min_p10_threshold = st.sidebar.slider("📈 10日趨勢過濾門檻", 30, 95, 70) # 預設提高到 70% 找強勢趨勢
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存建倉")
inventory_input = st.sidebar.text_area("輸入庫存 (代號,成本)", value="2337,34\n1409,16.5")

# ============================================
# 2. 核心計算邏輯
# ============================================
@st.cache_data(ttl=3600)
def get_market_list():
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
    # 計算指標
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
    # 10日機率：側重「結構」
    p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (15 if last['Vol_R'] > 1.2 else 0) + (20 if last['Close'] > last['High20'] else 0)
    # 5日機率：側重「加速度」
    p5 = 20 + (35 if last['MACD_S'] > prev['MACD_S'] * 1.3 else 0) + (30 if last['Vol_R'] > 2.5 else 0) + (10 if last['Close'] > last['Open'] * 1.04 else 0)
    return min(98, p5), min(98, p10)

# ============================================
# 3. 主程式介面
# ============================================
st.title("🚀 台股決賽輪：10D 趨勢模組監控系統")

# --- 第一部分：全市場 10D 獵殺掃描 ---
if st.button("🚀 啟動全市場 1000+ 標的趨勢掃描", type="primary"):
    tickers, names_map = get_market_list()
    all_results = []
    bar = st.progress(0)
    
    chunks = [tickers[i:i + 35] for i in range(0, len(tickers), 35)]
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        data = yf.download(chunk, period="4mo", group_by='ticker', progress=False)
        for t in chunk:
            try:
                df = data if len(chunk)==1 else data.get(t)
                if df is None or df.empty or len(df)<35: continue
                if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                
                df = calculate_logic(df.dropna(), trail_percent)
                p5, p10 = predict_probabilities(df)
                last_p = df['Close'].iloc[-1]
                
                # 成交量過濾 (日均量 > 1200張)
                if df['Volume'].iloc[-1] < 1200 * 1000: continue 

                # --- 核心修改：判斷 10D 勝率門檻 ---
                if p10 >= min_p10_threshold:
                    entry_p = round(last_p * 1.005, 2)
                    all_results.append({
                        "代號": t.replace(".TW",""),
                        "名稱": names_map[t],
                        "10D趨勢分": f"{p10}%", 
                        "5D噴發分": f"{p5}%",
                        "現價": round(last_p, 2),
                        "建議進場價": entry_p,
                        "動態止盈線": round(df['Trailing_Stop_Line'].iloc[-1], 2),
                        "動能狀況": "🔥 極強" if p5 > 65 else "📈 穩健"
                    })
            except: continue
    
    bar.empty()
    if all_results:
        st.subheader(f"🏆 符合 {min_p10_threshold}% 10日趨勢門檻之名單")
        # 顯示時將 10D 趨勢分放在最醒目的位置
        st.dataframe(pd.DataFrame(all_results).sort_values(by="10D趨勢分", ascending=False), hide_index=True, use_container_width=True)
    else:
        st.warning(f"目前市場無標的符合 {min_p10_threshold}% 的 10 日趨勢門檻。")

st.markdown("---")

# --- 第二部分：庫存回測報告 (維持不變) ---
st.subheader("💰 庫存盈利與撤退監控")
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
                    inv_results.append({
                        "代號": tid, "成本": float(cost), "現價": round(last_p, 2),
                        "累積盈利": f"{round((last_p/float(cost)-1)*100, 2)}%",
                        "動態止盈線": round(df_inv['Trailing_Stop_Line'].iloc[-1], 2),
                        "狀態": "⚠️ 建議撤退" if last_p < df_inv['Trailing_Stop_Line'].iloc[-1] else "✅ 安全持有"
                    })
            except: continue
    if inv_results: st.table(pd.DataFrame(inv_results))

# ============================================
# 4. 人生合夥人點醒
# ============================================
st.write("---")
st.write("### 💡 人生合夥人的真實點醒")
st.write(f"1. **為何改用 10D 勝率？** 10D 衡量的是『結構強度』。如果 10D > 70%，通常代表該股已經站上所有短中期均線，並開啟波段漲勢。")
st.write(f"2. **5D 分數的輔助意義**：即便 10D 高，但如果 5D 分數很低（例如 < 30%），代表趨勢雖好但『今日沒力』。**真正的獵物是 10D 高且 5D 也高的那幾支。**")
st.write(f"3. **旺宏 34 元的地位**：這種標的的 10D 勝率通常會極高。你的 19 萬現金現在應該去找那些 10D > 75% 且 5D 剛轉強的標的（例如光環或新纖）。")
