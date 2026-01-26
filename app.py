import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 系統環境設定 (確保連線不中斷)
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

st.set_page_config(page_title="鷹眼戰術中心", page_icon="🦅", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 鐵血左側面板 (強制固定位置)
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v11.5")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    st.subheader("⚙️ 掃描參數")
    min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
    target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
    min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
    st.divider()
    
    # --- 鐵血教條 (口號式) ---
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ **該走就走，頭也不回！**")
    st.error("💀 **妖股無情，心魔必斬！**")
    st.success("🎯 **守 SOP 是唯一勝算！**")
    st.info("💎 **本金是命，沒了就出局！**")

# ==========================================
# 2. 全市場 1000+ 樣本抓取與指標邏輯
# ==========================================
@st.cache_data(ttl=3600*12)
def get_stock_list_full():
    try:
        # 強制抓取證交所全部上市股票清單
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False, timeout=10)
        res.encoding = 'big5'
        df = pd.read_html(StringIO(res.text))[0]
        df.columns = df.iloc[0]
        # 過濾 ESVUFR (上市普通股)，這會確保樣本數在 1000 支以上
        df = df.iloc[1:][df['CFICode'] == 'ESVUFR']
        full_map = {p[0].strip(): p[1].strip() for p in (i.split('\u3000') for i in df['有價證券代號及名稱']) if len(p[0].strip()) == 4}
        return full_map
    except:
        st.error("全市場清單連線失敗，請檢查網路。")
        return {}

def calculate_indicators(df):
    close = df['Close']
    # RSI
    delta = close.diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = -delta.where(delta < 0, 0).rolling(14).mean()
    rsi = (100 - (100 / (1 + g/l))).iloc[-1]
    # MACD
    ema12 = close.ewm(span=12).mean(); ema26 = close.ewm(span=26).mean(); dif = ema12 - ema26; macd = dif.ewm(span=9).mean(); osc = dif - macd
    # KD
    rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
    k = rsv.ewm(com=2).mean().iloc[-1]
    return rsi, osc.iloc[-1], k

# ==========================================
# 3. 實體分頁邏輯
# ==========================================

# --- 市場掃描 ---
if page == "🎯 市場掃描":
    st.header("🎯 全市場 1000+ 樣本自動掃擊")
    if st.button("🚀 啟動掃描", type="primary"):
        stock_map = get_stock_list_full()
        res = [] 
        bar = st.progress(0); status = st.empty(); table_space = st.empty()
        total = len(stock_map)
        
        for i, (c, n) in enumerate(stock_map.items()):
            status.text(f"分析中 ({i+1}/{total}): {n} ({c})...")
            bar.progress((i+1)/total)
            try:
                df = yf.Ticker(f"{c}.TW").history(period="1y")
                if not df.empty and df['Volume'].iloc[-1] >= min_vol*1000:
                    last_p = df['Close'].iloc[-1]
                    # 5/10日勝率
                    ret5 = (df['Close'].shift(-5) - df['Close']) / df['Close'] * 100
                    ret10 = (df['Close'].shift(-10) - df['Close']) / df['Close'] * 100
                    w5 = (ret5 >= target_rise).sum() / ret5.count() * 100
                    w10 = (ret10 >= target_rise).sum() / ret10.count() * 100
                    
                    if w10 >= min_win10:
                        res.append({"選取": True, "代號": c, "名稱": n, "收盤價": last_p, "5日勝率%": w5, "10日勝率%": w10})
                        table_space.dataframe(pd.DataFrame(res).tail(3), hide_index=True)
            except: continue
        st.session_state.scan_results = pd.DataFrame(res)
        status.success(f"掃描完成！找到 {len(res)} 檔符合條件標的。")

    if st.session_state.scan_results is not None:
        st.subheader("📋 掃描戰果 (顯示中文名稱)")
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        
        if st.button("🏆 執行深度分析 (指標圖示化)"):
            st.divider()
            selected = edited_df[edited_df["選取"]]
            for _, row in selected.iterrows():
                df_all = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                rsi, osc, k = calculate_indicators(df_all)
                with st.container(border=True):
                    st.write(f"### {row['名稱']} ({row['代號']})")
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**RSI 強度計**\n{rsi:.1f} {'🚀' if rsi>50 else '📉'}")
                    c2.write(f"**MACD 油門**\n{'⛽ 滿油' if osc>0 else '🛑 減速'}")
                    c3.write(f"**KD 攻勢**\n{'🔥 續攻' if k>50 else '🧊 整理'}")
                    st.divider()
                    st.write(f"🛡️ **鐵血停損**: {row['收盤價']*0.95:.2f} | 🎯 **建議停利**: {row['收盤價']*1.1:.2f}")

# --- 庫存戰情 & 庫存管理邏輯 (同 v11.4 但修正中文顯示與 Rerun) ---
# ... (略)
