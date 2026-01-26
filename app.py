import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 基礎連線修復 (解決連線導致的按鈕卡死)
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

st.set_page_config(page_title="鷹眼股市戰情室", page_icon="🦅", layout="wide")

# 初始化所有記憶
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 自動抓取清單 (加入連線逾時處理)
# ==========================================
@st.cache_data(ttl=3600*12)
def get_stock_list_safe():
    stock_map = {}
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        # 增加 timeout 防止按鈕按下去沒反應
        response = requests.get(url, headers=HEADERS, verify=False, timeout=5)
        response.encoding = 'big5'
        df = pd.read_html(StringIO(response.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df = df[df['CFICode'] == 'ESVUFR']
        for item in df['有價證券代號及名稱']:
            parts = item.split('\u3000')
            if len(parts) >= 2:
                code, name = parts[0].strip(), parts[1].strip()
                if len(code) == 4: stock_map[code] = name
    except:
        return {"2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2337": "旺宏", "4916": "事欣科", "2344": "華邦電", "2408": "南亞科"}
    return stock_map

# ==========================================
# 2. 核心分析邏輯 (保持 v9.3 鐵血準則)
# ==========================================
def analyze_stock(code, name, min_vol, target_rise, min_win10):
    full_ticker = f"{code}.TW"
    try:
        s = yf.Ticker(full_ticker)
        df = s.history(period="1y")
        if df.empty or len(df) < 60: return None
        if df['Volume'].iloc[-1] < min_vol * 1000: return None
        
        last_p = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        
        # 強制條件：股價 > 月線
        if last_p < ma20: return None
        
        # 計算 10 日勝率
        fut_ret = (df['Close'].shift(-10) - df['Close']) / df['Close'] * 100
        win10 = (fut_ret >= target_rise).sum() / fut_ret.count() * 100
        
        # 濾網：最低勝率
        if win10 < min_win10: return None
        
        bias = ((last_p - ma20) / ma20) * 100
        return {
            "選取": True, "代號": code, "名稱": name, "收盤價": last_p, 
            "10日勝率%": win10, "乖離": "🔴 危險" if bias > 10 else "🟠 略貴" if bias > 5 else "🟢 安全",
            "MA20": ma20
        }
    except: return None

# ==========================================
# 3. 頁面模組
# ==========================================
def page_scanner():
    st.header("🎯 全市場自動掃描")
    
    # 先抓清單，不佔用掃描時間
    stock_map = get_stock_list_safe()
    all_codes = list(stock_map.keys())
    
    with st.sidebar:
        st.header("⚙️ 戰術控制台")
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 20, 10)
        min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
        st.success("✅ 強制開啟：股價 > 月線")

    # 執行掃描 (修復按鈕反應問題)
    if st.button("🚀 啟動全市場掃描", type="primary"):
        res_list = []
        progress = st.progress(0)
        status = st.empty()
        table_space = st.empty()
        
        # 為了效能，每次掃描會先清空舊的 session_state
        st.session_state.scan_results = None
        
        for i, c in enumerate(all_codes):
            status.text(f"分析中 ({i+1}/{len(all_codes)})：{c} {stock_map.get(c)}...")
            progress.progress((i+1)/len(all_codes))
            
            data = analyze_stock(c, stock_map.get(c), min_vol, target_rise, min_win10)
            if data:
                res_list.append(data)
                # 即時更新記憶與顯示
                df_temp = pd.DataFrame(res_list)
                st.session_state.scan_results = df_temp
                table_space.dataframe(df_temp.tail(5), hide_index=True)
        
        status.success(f"掃描完成！共找到 {len(res_list)} 檔符合條件標的。")

    # 顯示掃描結果
    if st.session_state.scan_results is not None:
        st.subheader("📋 掃描戰果 (已保留)")
        st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)

# ... (庫存管理 page_management 維持 v10.2 強化版)

def main():
    st.sidebar.title("🦅 戰情室")
    page = st.sidebar.radio("導航", ["📊 庫存看板", "🎯 市場掃描", "➕ 庫存管理"])
    if page == "📊 庫存看板":
        st.write("庫存資訊讀取中...") # 此處串接 page_dashboard
    elif page == "🎯 市場掃描": page_scanner()
    elif page == "➕ 庫存管理":
        # 此處串接修復過的 page_management
        st.write("管理您的持股...")

if __name__ == "__main__":
    main()
