import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import urllib3

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統設定
# ============================================
st.set_page_config(page_title="台股獵殺系統 - 動態止盈版", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 190000  # 你的可用銀彈

# ============================================
# 2. 核心計算邏輯
# ============================================
def calculate_metrics(df, trail_percent):
    """計算技術指標與動態止盈點位"""
    if len(df) < 20: return df
    
    close = df['Close']
    # 5D / 10D 均線
    df['MA5'] = close.rolling(5).mean()
    df['MA10'] = close.rolling(10).mean()
    
    # 瘋狗浪動能：成交量比
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    
    # --- 動態止盈核心邏輯 ---
    # 追蹤區間內的最高價 (Peak)
    df['Rolling_Peak'] = df['High'].cummax() 
    
    # 計算應出場點位 (以最高價回落指定百分比)
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - trail_percent / 100)
    
    # 判斷目前是否已觸發止盈 (收盤價跌破止盈線)
    df['Exit_Signal'] = df['Close'] < df['Trailing_Stop_Line']
    
    return df

@st.cache_data(ttl=3600)
def get_market_list():
    """抓取證交所股票清單"""
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

# ============================================
# 3. 主介面控制台
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
st.session_state.cash = st.sidebar.number_input("當前可用銀彈 (NTD)", value=st.session_state.cash)

# 動態止盈參數設定
trail_percent = st.sidebar.slider("動態止盈回落百分比 (%)", 3.0, 15.0, 7.0, step=0.5)
st.sidebar.info(f"💡 當股價從最高點回落 {trail_percent}% 時，系統將提示撤退。")

# ============================================
# 4. 執行分析
# ============================================
st.title("🚀 台股決賽輪：5D/10D 動態止盈監控系統")

if st.button("🚀 啟動全市場掃描與利潤鎖定", type="primary"):
    tickers, names_map = get_market_list()
    all_results = []
    bar = st.progress(0)
    
    # 為了演示速度，此處取前 50 支，實戰時可移除切片 [0:50]
    test_tickers = tickers[0:100] 
    
    for i, t in enumerate(test_tickers):
        bar.progress((i + 1) / len(test_tickers))
        try:
            df = yf.download(t, period="3mo", progress=False)
            if df.empty or len(df) < 20: continue
            
            # 數據清洗
            if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(1, axis=1)
            
            # 運算指標
            df = calculate_metrics(df, trail_percent)
            last_row = df.iloc[-1]
            
            # 只顯示符合 5D/10D 多頭排列 或 強勢噴發的標的
            if last_row['Close'] > last_row['MA5'] or last_row['Vol_R'] > 1.5:
                all_results.append({
                    "代號": t.replace(".TW",""),
                    "名稱": names_map[t],
                    "現價": round(last_row['Close'], 2),
                    "區間最高價": round(last_row['Rolling_Peak'], 2),
                    "應出場點位": round(last_row['Trailing_Stop_Line'], 2),
                    "距離止盈線": f"{round((last_row['Close']/last_row['Trailing_Stop_Line']-1)*100, 2)}%",
                    "狀態": "⚠️ 觸發止盈" if last_row['Exit_Signal'] else "✅ 安全持有"
                })
        except: continue

    bar.empty()
    
    if all_results:
        res_df = pd.DataFrame(all_results)
        
        # 顯示警示區域
        st.subheader("🚨 即時利潤鎖定監控")
        exit_targets = res_df[res_df['狀態'] == "⚠️ 觸發止盈"]
        if not exit_targets.empty:
            st.error(f"警告：以下標的已從最高點回落超過 {trail_percent}%，建議立即鎖定利潤！")
            st.table(exit_targets)
        else:
            st.success(f"目前監控標的均未觸發 {trail_percent}% 動態止盈線。")

        # 顯示所有標的數據
        st.markdown("---")
        st.subheader("📊 掃描標的列表")
        st.dataframe(res_df, use_container_width=True, hide_index=True)
    else:
        st.warning("目前市場無符合動能條件之標的。")

# ============================================
# 5. 人生合夥人點醒
# ============================================
st.write("---")
st.write("### 💡 人生合夥人的真實點醒")
st.write(f"1. **為何要用區間最高價？** 因為我們不預設高點。只要股價創高，你的`應出場點位`就會像影子一樣跟上去。")
st.write(f"2. **紀律高於一切**：當`現價`低於`應出場點位`時，格子會變紅色。這不是建議，是獵人的撤退指令。")
st.write(f"3. **旺宏 (34元) 專用策略**：對於這種翻倍股，你可以將回落 % 調高至 10-12%，給它更大的震盪空間，才不會被洗掉。")
