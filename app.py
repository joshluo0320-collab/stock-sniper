import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup

# ============================================
# 1. 系統與 UI 設定
# ============================================
st.set_page_config(page_title="台股決賽輪 - 終極修復版", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
min_p10_threshold = st.sidebar.slider("📈 10日趨勢門檻 (%)", 5, 95, 10) # 調低至 5% 測試
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)
min_vol_lots = st.sidebar.slider("🌊 流動性門檻 (5日均張)", 0, 3000, 100) # 調低至 100 張測試

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("庫存 (代號,成本)", value="2337,34\n1409,16.5")

# ============================================
# 2. 數據模組
# ============================================
def get_full_market_list():
    """抓取清單，若失敗則回傳備援清單"""
    tickers, names = [], {}
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2" # 上市
        res = requests.get(url, timeout=5)
        res.encoding = 'big5'
        soup = BeautifulSoup(res.text, 'lxml')
        for row in soup.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) > 0:
                text = cols[0].text.strip().split()
                if len(text) >= 2 and len(text[0]) == 4 and text[0].isdigit():
                    t = f"{text[0]}.TW"
                    tickers.append(t); names[t] = text[1]
    except:
        pass
    
    if not tickers: # 備援機制：如果網頁抓不到，至少保證能搜這幾支
        backup = ["2330.TW", "2337.TW", "1409.TW", "2368.TW", "3234.TW", "2317.TW", "2454.TW", "3037.TW"]
        names = {t: "熱門股" for t in backup}
        return backup, names
    return tickers, names

def calculate_logic(df, tp_pct, min_vol):
    if df.empty or len(df) < 10: return None
    
    # 🌊 流動性過濾
    avg_vol = df['Volume'].tail(5).mean() / 1000
    if avg_vol < min_vol: return None

    close = df['Close']
    df['MACD_S'] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    return df

# ============================================
# 3. 執行介面
# ============================================
st.title("🛡️ 台股獵殺：全自動修復監控系統")

# --- 庫存區 ---
if st.button("📊 檢視我的庫存 (旺宏/新纖)"):
    items = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    results = []
    for tid, cost in items:
        df = yf.download(f"{tid.strip()}.TW", period="1y", progress=False)
        if not df.empty:
            df = calculate_logic(df, trail_percent, 0)
            last_p = float(df['Close'].iloc[-1])
            stop_p = float(df['Trailing_Stop_Line'].iloc[-1])
            results.append({"代號": tid, "現價": round(last_p, 2), "止盈線": round(stop_p, 2), "狀態": "✅" if last_p > stop_p else "⚠️"})
    st.table(pd.DataFrame(results))

# --- 掃描區 ---
if st.button("🔴 開始全市場掃描 (最新優化版)", type="primary"):
    all_tickers, names_map = get_full_market_list()
    st.info(f"成功加載 {len(all_tickers)} 支標的，開始計算...")
    
    final_results = []
    progress_bar = st.progress(0)
    
    # 縮小掃描範圍至前 200 支 (測試用) 或改批次
    test_tickers = all_tickers[:300] 
    
    for i, t in enumerate(test_tickers):
        progress_bar.progress((i + 1) / len(test_tickers))
        df = yf.download(t, period="6mo", progress=False)
        if df.empty: continue
        
        # 處理 yfinance 可能的 MultiIndex
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df_processed = calculate_logic(df.dropna(), trail_percent, min_vol_lots)
        if df_processed is not None:
            last = df_processed.iloc[-1]
            p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (20 if last['Close'] > last['High20'] else 0)
            if p10 >= min_p10_threshold:
                final_results.append({
                    "代號": t.replace(".TW",""), "名稱": names_map.get(t, "未知"),
                    "趨勢": f"{int(p10)}%", "現價": round(float(last['Close']), 2),
                    "均張": int(df['Volume'].tail(5).mean()/1000)
                })
    
    if final_results:
        st.dataframe(pd.DataFrame(final_results).sort_values(by="趨勢", ascending=False))
    else:
        st.warning("完全沒搜到標的，請將『流動性門檻』調低到 0 試試看。")
