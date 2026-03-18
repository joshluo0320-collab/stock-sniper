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
st.set_page_config(page_title="台股獵殺系統 - 5D/10D 動態版", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 190000 

# ============================================
# 2. 核心計算與邏輯
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

def calculate_logic(df, trail_percent):
    if len(df) < 40: return df
    close = df['Close']
    # MACD 動能斜率
    exp12 = close.ewm(span=12, adjust=False).mean()
    exp26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_S'] = df['MACD'].diff() 
    # 成交量比 (瘋狗浪指標)
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    # 均線
    df['MA5'] = close.rolling(5).mean()
    df['MA10'] = close.rolling(10).mean()
    df['MA20'] = close.rolling(20).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    
    # --- 動態止盈邏輯 ---
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - trail_percent / 100)
    df['Exit_Signal'] = df['Close'] < df['Trailing_Stop_Line']
    
    return df

def predict_probabilities(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # 10日機率 (趨勢)
    p10 = 40
    if last['MACD_S'] > 0: p10 += 20
    if last['Vol_R'] > 1.2: p10 += 15
    if last['Close'] > last['High20']: p10 += 20
    # 5日機率 (噴發)
    p5 = 20
    if last['MACD_S'] > prev['MACD_S'] * 1.3: p5 += 35 
    if last['Vol_R'] > 2.5: p5 += 30 
    if last['Close'] > last['Open'] * 1.04: p5 += 10 
    return min(98, p5), min(98, p10)

# ============================================
# 3. 介面控制台
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
st.session_state.cash = st.sidebar.number_input("當前可用銀彈 (NTD)", value=st.session_state.cash)

# 重新回復：過濾門檻與動態百分比
min_p5_threshold = st.sidebar.slider("🔥 5日機率過濾門檻", 30, 95, 45)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.write(f"當前策略：\n1. 噴發機率 > {min_p5_threshold}% 才推薦\n2. 從最高點回落 {trail_percent}% 即撤退")

# ============================================
# 4. 主程式執行
# ============================================
st.title("🚀 台股決賽輪：5D / 10D 雙模動態監控")
st.info(f"可用銀彈：NT$ {int(st.session_state.cash):,} | 監控模式：動態止盈追蹤中")

if st.button("🚀 啟動全市場獵殺掃描", type="primary"):
    tickers, names_map = get_market_list()
    all_results = []
    bar = st.progress(0)
    
    # 分塊抓取提高效率
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

                # 重新加入：5日門檻過濾
                if p5 >= min_p5_threshold:
                    entry_price = round(last_p * 1.005, 2)
                    suggested_inv = st.session_state.cash * 0.2
                    shares = int(suggested_inv / (entry_price * 1000))
                    
                    all_results.append({
                        "5日勝率": p5, "代號": t.replace(".TW",""), "名稱": names_map[t],
                        "現價": round(last_p, 2),
                        "區間最高": round(df['Rolling_Peak'].iloc[-1], 2),
                        "動態止盈線": round(df['Trailing_Stop_Line'].iloc[-1], 2),
                        "建議買進張數": shares,
                        "狀態": "⚠️ 建議撤退" if df['Exit_Signal'].iloc[-1] else "✅ 動能持續"
                    })
            except: continue

    bar.empty()
    if all_results:
        res_df = pd.DataFrame(all_results).sort_values(by="5日勝率", ascending=False)
        
        # 顯示 Top 5
        st.subheader(f"🏆 符合 {min_p5_threshold}% 門檻之前五強")
        cols = st.columns(len(res_df.head(5)))
        for i, row in enumerate(res_df.head(5).to_dict('records')):
            with cols[i]:
                st.metric(f"{row['代號']} {row['名稱']}", f"{row['現價']}", f"{row['5日勝率']}%")
                st.write(f"🛑 止盈線: {row['動態止盈線']}")
                if row['狀態'] == "⚠️ 建議撤退":
                    st.error("觸發回落！")
                else:
                    st.success("動能安全")
        
        st.markdown("---")
        st.subheader("📊 完整監控清單")
        st.dataframe(res_df, use_container_width=True, hide_index=True)
    else:
        st.warning(f"目前市場無標的通過 {min_p5_threshold}% 的噴發測試。")

# ============================================
# 5. 人生合夥人點醒
# ============================================
st.write("---")
st.write("### 💡 人生合夥人的真實點醒")
st.write(f"1. **門檻的意義**：你設定的 **{min_p5_threshold}%** 門檻是你的「防彈衣」。低於這個數字的股票，無論故事多好聽，都代表動能不足，不值得你投入那 19 萬。")
st.write(f"2. **雙重防線**：現在系統會幫你檢查『進場機率』與『出場位置』。進場看勝率，持有看回落。")
