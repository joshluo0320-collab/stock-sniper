import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統與 UI 設定
# ============================================
st.set_page_config(page_title="台股決賽輪 - 鋼鐵監控系統", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
min_p10_threshold = st.sidebar.slider("📈 10日趨勢門檻 (%)", 10, 95, 40)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)
# 🛡️ 流動性門檻：排除像承業醫這種沒量的股票
min_vol_lots = st.sidebar.slider("🌊 流動性門檻 (5日均張)", 0, 3000, 500)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存設定")
inventory_input = st.sidebar.text_area("格式: 代號,成本 (每行一筆)", value="2337,34\n1409,16.5")

# ============================================
# 2. 核心運算與過濾邏輯
# ============================================
def calculate_logic(df, tp_pct, min_vol):
    if len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 🌊 流動性過濾：5日平均成交量 (張)
    avg_vol_lots = (df['Volume'].rolling(5).mean().iloc[-1]) / 1000
    if avg_vol_lots < min_vol:
        return None

    close = df['Close']
    df['MACD_S'] = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff() 
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    return df

@st.cache_data(ttl=3600)
def get_full_market():
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    tickers, names = [], {}
    for url in urls:
        res = requests.get(url, verify=False)
        res.encoding = 'big5'
        soup = BeautifulSoup(res.text, 'lxml')
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) > 0:
                text = cols[0].text.strip().split()
                if len(text) >= 2 and len(text[0]) == 4 and text[0].isdigit():
                    t = f"{text[0]}.TW" if "strMode=2" in url else f"{text[0]}.TWO"
                    tickers.append(t); names[t] = text[1]
    return tickers, names

# ============================================
# 3. 畫面顯示邏輯
# ============================================
st.title("🛡️ 台股決賽輪：全市場掃描與庫存動態監控")

# --- 第一區塊：我的庫存即時報告 ---
st.subheader("💰 我的庫存盈虧與撤退監控")
if st.button("📊 重新整理庫存數據"):
    inv_data = []
    items = [line.split(',') for line in inventory_input.split('\n') if ',' in line]
    if items:
        # 為了速度，個別抓取庫存資料
        for tid, cost in items:
            t_code = f"{tid.strip()}.TW" # 預設上市，若沒資料會嘗試上櫃
            df_inv = yf.download(t_code, period="1y", progress=False)
            if df_inv.empty: 
                t_code = f"{tid.strip()}.TWO"
                df_inv = yf.download(t_code, period="1y", progress=False)
            
            if not df_inv.empty:
                df_inv = calculate_logic(df_inv.dropna(), trail_percent, 0) # 庫存不套用流動性過濾
                last_p = float(df_inv['Close'].iloc[-1])
                stop_p = float(df_inv['Trailing_Stop_Line'].iloc[-1])
                profit = (last_p / float(cost) - 1) * 100
                inv_data.append({
                    "代號": tid, "成本": float(cost), "現價": round(last_p, 2),
                    "累計損益": f"{round(profit, 2)}%",
                    "動態止盈線": round(stop_p, 2),
                    "狀態": "⚠️ 建議撤退" if last_p < stop_p else "✅ 穩健持有"
                })
        if inv_data: st.table(pd.DataFrame(inv_data))
    else:
        st.info("請在左側輸入庫存代號與成本。")

st.markdown("---")

# --- 第二區塊：全市場獵殺掃描 ---
st.subheader(f"🔍 全市場 {min_p10_threshold}% 趨勢標的篩選")
if st.button("🔴 開始全市場掃描 (排除低量股)", type="primary"):
    all_tickers, names_map = get_full_market()
    st.write(f"正在掃描全台股 {len(all_tickers)} 支標的...")
    
    results = []
    bar = st.progress(0)
    # 批次下載以加速
    chunks = [all_tickers[i:i + 50] for i in range(0, len(all_tickers), 50)]
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        data = yf.download(chunk, period="4mo", group_by='ticker', progress=False)
        for t in chunk:
            df = data[t] if len(chunk) > 1 else data
            if df is None or df.empty: continue
            df = calculate_logic(df.dropna(), trail_percent, min_vol_lots)
            if df is not None:
                # 簡單趨勢評分
                last = df.iloc[-1]
                p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (20 if last['Close'] > last['High20'] else 0)
                if p10 >= min_p10_threshold:
                    results.append({
                        "代號": t.split(".")[0], "名稱": names_map[t],
                        "趨勢強度": f"{int(p10)}%", "現價": round(float(last['Close']), 2),
                        "5日均張": int(df['Volume'].rolling(5).mean().iloc[-1] / 1000),
                        "動態止盈線": round(float(last['Trailing_Stop_Line']), 2)
                    })
    bar.empty()
    if results:
        st.dataframe(pd.DataFrame(results).sort_values(by="趨勢強度", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning("當前市場無符合門檻之標的。")
