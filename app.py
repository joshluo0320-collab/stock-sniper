import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 基礎設定
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0'}

st.set_page_config(page_title="鷹眼戰術中心", page_icon="🦅", layout="wide")

# 初始化 Session 記憶
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 左側控制面板 (Sidebar)
# ==========================================

with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v11.0")
    
    # 分頁導航
    page = st.radio("📡 戰情分頁", ["📊 庫存戰情", "🎯 全市場掃描", "➕ 庫存管理"])
    
    st.divider()
    
    # 參數設定 (僅在市場掃描時顯示或作為全域設定)
    st.subheader("⚙️ 掃描變因")
    min_vol = st.number_input("🌊 最低成交量 (張)", value=1000, step=100)
    target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
    min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
    
    st.divider()
    
    # 鐵血紀律口號區 (精神提醒)
    st.error("🛑 **鐵血紀律中心**")
    st.markdown("""
    ### 🛡️ 戰勝心魔
    * **不看損益，只看紀律！**
    * **該走就走，頭也不回！**
    * **妖股無情，唯快不破！**
    * **本金是子彈，沒了就出局！**
    
    ### 🎯 執行準則
    * **遵守 SOP 是唯一的勝算！**
    * **停損是為了下一次的狙擊！**
    * **貪婪是妖股的毒藥！**
    """)
    st.divider()

# ==========================================
# 2. 主畫面模組
# ==========================================

# --- 分頁: 庫存戰情 ---
if page == "📊 庫存戰情":
    st.header("📊 即時損益監控 (紅漲綠跌)")
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
                        st.markdown(f"🎯 **目標停利**：<span style='color:red;'>{last_p * 1.1:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"🛡️ **鐵血停損**：<span style='color:green;'>{s['cost'] * 0.95:.2f}</span>", unsafe_allow_html=True)
            except: st.error(f"{s['code']} 連線逾時")

# --- 分頁: 全市場掃描 ---
elif page == "🎯 全市場掃描":
    st.header("🎯 1007 支全市場自動掃擊")
    if st.button("🚀 啟動掃描", type="primary"):
        st.warning("掃描進行中... 請遵照左側紀律執行！")
        # 掃描邏輯區 (略)
    if st.session_state.scan_results is not None:
        st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)

# --- 分頁: 庫存管理 ---
elif page == "➕ 庫存管理":
    st.header("➕ 持股名單優化")
    with st.form("add_stock", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        code, name = c1.text_input("代號"), c2.text_input("名稱")
        cost, shares = c3.number_input("成本", value=0.0), c4.number_input("張數", value=1)
        if st.form_submit_button("執行存入"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
            st.rerun()
    
    st.divider()
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']} | {s['shares']/1000} 張")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx)
            st.rerun()
