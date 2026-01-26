import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 基礎設定 (SSL 與 Headers)
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0'}

st.set_page_config(page_title="鷹眼戰術中心", page_icon="🦅", layout="wide")

# 初始化記憶
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 自動抓取清單函數 (確保 1007 支版本)
# ==========================================
@st.cache_data(ttl=3600*12)
def get_stock_list_full():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False, timeout=5)
        res.encoding = 'big5'
        df = pd.read_html(StringIO(res.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:][df['CFICode'] == 'ESVUFR']
        return {p[0].strip(): p[1].strip() for p in (i.split('\u3000') for i in df['有價證券代號及名稱']) if len(p[0].strip()) == 4}
    except: return {"2330": "台積電", "2337": "旺宏", "4916": "事欣科", "2344": "華邦電", "2408": "南亞科"}

# ==========================================
# 2. 左側控制面板 (Sidebar) - 控制面板歸位
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v11.1")
    page = st.radio("📡 戰情分頁", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    
    st.subheader("⚙️ 掃描變因")
    min_vol = st.number_input("🌊 最低成交量 (張)", value=1000, step=100)
    target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
    min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
    
    st.divider()
    st.error("🛑 **鐵血紀律中心**")
    st.markdown("""
    ### 🛡️ 戰勝心魔
    * **不看損益，只看紀律！**
    * **該走就走，頭也不回！**
    * **妖股無情，唯快不破！**
    
    ### 🎯 執行準則
    * **遵守 SOP 是唯一的勝算！**
    * **停損是為了下一次的狙擊！**
    """)

# ==========================================
# 3. 分頁實體化邏輯 (修復按鈕無反應)
# ==========================================

# --- 分頁: 庫存戰情 ---
if page == "📊 庫存戰情":
    st.header("📊 庫存即時戰情")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                h = t.history(period="10d")
                if not h.empty:
                    last_p, prev_p = h.iloc[-1]['Close'], h.iloc[-2]['Close']
                    p_color = "red" if last_p >= prev_p else "green"
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p:.2f}</span>", unsafe_allow_html=True)
                        st.write(f"🎯 **目標停利**: {last_p * 1.1:.2f}")
                        st.write(f"🛡️ **鐵血停損**: {s['cost'] * 0.95:.2f}")
            except: st.error(f"{s['code']} 更新失敗")

# --- 分頁: 市場掃描 (修正按鈕無反應關鍵點) ---
elif page == "🎯 市場掃描":
    st.header("🎯 全市場自動掃描")
    if st.button("🚀 啟動掃擊", type="primary"):
        stock_map = get_stock_list_full()
        res = []
        bar = st.progress(0); status = st.empty(); table_space = st.empty()
        for i, (c, n) in enumerate(stock_map.items()):
            status.text(f"分析中: {c} {n}...")
            bar.progress((i+1)/len(stock_map))
            try:
                df = yf.Ticker(f"{c}.TW").history(period="60d")
                if not df.empty and df['Volume'].iloc[-1] >= min_vol*1000:
                    last_p = df['Close'].iloc[-1]
                    ma20 = df['Close'].rolling(20).mean().iloc[-1]
                    if last_p >= ma20: # 鐵血濾網：月線之上
                        fut_ret = (df['Close'].shift(-10) - df['Close']) / df['Close'] * 100
                        win10 = (fut_ret >= target_rise).sum() / fut_ret.count() * 100
                        if win10 >= min_win10:
                            res.append({"選取": True, "代號": c, "名稱": n, "收盤價": last_p, "10日勝率%": win10})
                            table_space.dataframe(pd.DataFrame(res).tail(3), hide_index=True)
            except: continue
        st.session_state.scan_results = pd.DataFrame(res)
        status.success(f"掃描完成！共找到 {len(res)} 檔。")

    if st.session_state.scan_results is not None:
        st.subheader("📋 掃描戰果")
        st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)

# --- 分頁: 庫存管理 ---
elif page == "➕ 庫存管理":
    st.header("➕ 持股庫存管理")
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        code, name = c1.text_input("代號"), c2.text_input("名稱")
        cost, shares = c3.number_input("成本", value=0.0), c4.number_input("張數", value=1)
        if st.form_submit_button("確認存入"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
            st.rerun()
    
    st.subheader("📋 庫存清單")
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']} | {s['shares']/1000} 張")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx)
            st.rerun()
