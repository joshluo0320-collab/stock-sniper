import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import urllib3

# 關閉連線警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 系統設定
# ============================================
st.set_page_config(page_title="台股 10D/10% 爆發預測系統", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000  

# ============================================
# 核心數據抓取 (連線證交所全市場)
# ============================================
@st.cache_data(ttl=86400)
def get_full_market_list():
    """核實 1：連線證交所，抓取台股 1000+ 支上市股票"""
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False)
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        tickers = []
        names_map = {}
        for index, row in df.iterrows():
            code_name = str(row['有價證券代號及名稱'])
            parts = code_name.split()
            # 確保是 4 位數代號的股票
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                ticker = f"{parts[0]}.TW"
                tickers.append(ticker)
                names_map[ticker] = parts[1]
        return tickers, names_map
    except:
        return [], {}

def calculate_logic(df):
    """計算判斷預測所需的各項指標"""
    if len(df) < 35: return df
    
    # 推進力 (MACD 斜率)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_Slope'] = df['MACD'].diff() 

    # 噴發空間 (布林寬度)
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Std'] = df['Close'].rolling(window=20).std()
    df['BB_Width'] = (df['Std'] * 4) / df['MA20']
    
    # 便宜程度 (RSI)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    return df

# ============================================
# 核實 2：直白、淺顯、易懂的分析邏輯
# ============================================
def predict_burst(df):
    """預測未來 10 日內漲 10% 的可能性"""
    last = df.iloc[-1]
    prob = 30 # 基礎分
    
    analysis_text = []
    
    # 1. 推進力 (MACD)
    if last['MACD_Slope'] > 0:
        prob += 20
        analysis_text.append("🔥 加速前進中")
    else:
        analysis_text.append("💤 目前休息中")
        
    # 2. 空間 (突破 20 日高點)
    highest_recent = df['High'].rolling(20).max().iloc[-2]
    if last['Close'] > highest_recent:
        prob += 20
        analysis_text.append("🚀 衝破天花板")
    else:
        analysis_text.append("🧱 上方有阻力")
        
    # 3. 能量 (成交量)
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if last['Volume'] > vol_ma5 * 1.5:
        prob += 15
        analysis_text.append("🔋 動能爆發")
    
    # 4. 準備度 (盤整多久了)
    if last['BB_Width'] < df['BB_Width'].rolling(20).mean().iloc[-1]:
        prob += 10
        analysis_text.append("📦 壓縮完畢")

    # 5. 回檔修正 (RSI)
    if last['RSI'] > 75: 
        prob -= 15 # 過熱風險
        analysis_text.append("⚠️ 太熱小心")

    return min(98, prob), " | ".join(analysis_text)

# ============================================
# 介面設計
# ============================================
st.sidebar.header("🕹️ 控制台")
st.sidebar.write(f"💰 目前可用銀彈：${int(st.session_state.cash):,}")

price_range = st.sidebar.slider("股票單價範圍", 10, 300, (20, 150))
min_vol = st.sidebar.number_input("每日最低成交量 (張)", value=1000)
min_prob = st.sidebar.slider("爆發機率門檻 (%)", 40, 95, 65)

st.title("📈 台股全市場「10日/10%」爆發預測")
st.info("系統將連線證交所分析 1,000+ 支股票，篩選出具備『短期噴發基因』的標的。")

if st.button("🚀 開始全市場掃描 (約需 1 分鐘)", type="primary"):
    tickers, names_map = get_full_market_list()
    
    if not tickers:
        st.error("連線證交所失敗，請檢查網路。")
        st.stop()
        
    results = []
    bar = st.progress(0)
    status_text = st.empty()
    
    # 分段下載數據防止崩潰
    chunk_size = 25
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        status_text.text(f"正在分析第 {i*chunk_size} ~ {(i+1)*chunk_size} 支股票...")
        
        try:
            data = yf.download(chunk, period="3mo", group_by='ticker', progress=False, threads=False)
            for t in chunk:
                try:
                    df = data if len(chunk) == 1 else data.get(t)
                    if df is None or df.empty or len(df) < 20: continue
                    if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                    
                    df = df.dropna(subset=['Close'])
                    df = calculate_logic(df)
                    
                    last_p = df['Close'].iloc[-1]
                    # 基礎過濾
                    if not (price_range[0] <= last_p <= price_range[1]): continue
                    if df['Volume'].iloc[-1] < min_vol * 1000: continue
                    
                    # 爆發預測
                    prob, analysis = predict_burst(df)
                    
                    if prob >= min_prob:
                        results.append({
                            "代號": t.replace(".TW", ""),
                            "股票名稱": names_map.get(t, t),
                            "預測爆發力": prob,
                            "目前價格": last_p,
                            "白話分析報告": analysis,
                            "操作建議": "🔥 重點跟進" if prob >= 80 else "👀 放入清單"
                        })
                except: continue
        except: continue

    bar.empty()
    status_text.empty()

    if results:
        df_res = pd.DataFrame(results).sort_values(by="預測爆發力", ascending=False)
        st.success(f"掃描完成！從 1,000+ 支股票中挑選出 {len(results)} 檔具備爆發潛力的標的。")
        
        st.dataframe(
            df_res,
            column_config={
                "預測爆發力": st.column_config.ProgressColumn(
                    "未來10日漲10%機率",
                    help="分數越高，代表動能與空間越充足",
                    format="%d%%",
                    min_value=0,
                    max_value=100,
                ),
                "目前價格": st.column_config.NumberColumn("價格", format="$%.1f"),
                "白話分析報告": st.column_config.TextColumn("📊 技術診斷", width="large")
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("當前市場動能不足，沒有符合高爆發條件的股票。")

st.markdown("---")
st.subheader("💡 數據說明 (直白版)")
c1, c2, c3 = st.columns(3)
c1.write("**🔥 推進力**：代表買的人力道越來越大，沒有熄火。")
c2.write("**🚀 衝破天花板**：前方沒有人被套牢，漲起來沒阻力。")
c3.write("**🔋 動能爆發**：今天進場的人比平常多很多，大家都在買。")
