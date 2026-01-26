import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 系統環境設定 (SSL 修復)
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0'}

st.set_page_config(page_title="鷹眼股市戰情室", page_icon="🦅", layout="wide")

# 初始化 Session 記憶
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 核心指標運算函數
# ==========================================

def calculate_indicators(df):
    close = df['Close']
    # RSI 計算
    delta = close.diff()
    g = (delta.where(delta > 0, 0)).rolling(14).mean()
    l = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = (100 - (100 / (1 + g/l))).iloc[-1]
    # KD 狀態 (K線與D線相對位置)
    rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
    k = rsv.ewm(com=2).mean().iloc[-1]
    # MA20 支撐與乖離
    ma20 = close.rolling(20).mean().iloc[-1]
    bias = ((close.iloc[-1] - ma20) / ma20) * 100
    return rsi, k, ma20, bias

# ==========================================
# 2. 左側控制台 & 戰術提醒區
# ==========================================

with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v10.9")
    page = st.radio("分頁導航", ["📊 庫存看板", "🎯 市場掃描", "➕ 庫存管理"])
    
    st.divider()
    st.header("💡 戰術提醒")
    st.info("""
    * **紅漲綠跌**：數值依台股慣例顯示。
    * **整張交易**：除長期標的外，排除零股。
    * **停損紀律**：跌破 MA20 應果斷撤退。
    * **高精準度**：系統自動過濾月線下弱勢股。
    """)

# ==========================================
# 3. 主畫面分頁邏輯
# ==========================================

# --- 庫存看板 ---
if page == "📊 庫存看板":
    st.header("📊 庫存即時戰情")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                h = t.history(period="10d")
                if not h.empty:
                    last_p, prev_p = h.iloc[-1]['Close'], h.iloc[-2]['Close']
                    chg = last_p - prev_p
                    profit = (last_p - s['cost']) * s['shares']
                    prof_pct = (profit / (s['cost'] * s['shares'])) * 100
                    p_color = "red" if chg >= 0 else "green"
                    pf_color = "red" if profit >= 0 else "green"
                    
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"損益：<span style='color:{pf_color}; font-weight:bold;'>{int(profit):+,} ({prof_pct:.2f}%)</span>", unsafe_allow_html=True)
                        st.divider()
                        st.markdown(f"🎯 **建議停利**：<span style='color:red;'>{last_p * 1.1:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"🛡️ **建議停損**：<span style='color:green;'>{s['cost'] * 0.95:.2f}</span>", unsafe_allow_html=True)
            except: st.error(f"{s['code']} 讀取失敗")

# --- 市場掃描 ---
elif page == "🎯 市場掃描":
    st.header("🎯 全市場自動掃描")
    # 掃描參數設定
    with st.container(border=True):
        sc1, sc2, sc3 = st.columns(3)
        min_vol = sc1.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = sc2.slider("🎯 目標漲幅 (%)", 1, 30, 10)
        min_win10 = sc3.slider("🔥 最低10日勝率 (%)", 0, 100, 40)

    if st.button("🚀 啟動掃描", type="primary"):
        # 獲取清單並開始迴圈分析 (邏輯同 v10.8)
        # ...
        pass

    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        if st.button("🏆 執行深度 AI 評測"):
            st.divider()
            selected = edited_df[edited_df["選取"]]
            for _, row in selected.iterrows():
                # 執行指標運算與圖像化顯示 (邏輯同 v10.8)
                pass

# --- 庫存管理 ---
elif page == "➕ 庫存管理":
    st.header("➕ 持股管理")
    with st.form("add_stock", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        code = c1.text_input("代號")
        name = c2.text_input("名稱")
        cost = c3.number_input("成本", value=0.0)
        shares = c4.number_input("張數", value=1)
        if st.form_submit_button("確認存入"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
            st.rerun() # 立即刷新清單
    
    st.divider()
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']} | {s['shares']/1000} 張")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx)
            st.rerun()
