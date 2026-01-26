import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from io import StringIO

# ==========================================
# 0. 系統環境設定
# ==========================================
st.set_page_config(page_title="鷹眼戰術中心", page_icon="🦅", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 鐵血紀律教條 (口號式提醒)
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v13.4")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ **該走就走，頭也不回！**")
    st.error("💀 **妖股無情，心魔必斬！**")
    st.success("🎯 **守 SOP 是唯一勝算！**")
    st.info("💎 **本金是命，沒了就出局！**")

# ==========================================
# 2. 分頁功能實體化
# ==========================================

# --- [略: 庫存戰情與市場掃描邏輯同 v13.3] ---

# --- 分頁 3: 庫存管理 (正式修復實體功能) ---
if page == "➕ 庫存管理":
    st.header("➕ 庫存名單優化")
    
    # 新增功能
    with st.expander("➕ 手動新增持股", expanded=True):
        with st.form("add_stock_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            new_code = c1.text_input("代號 (例: 1623)")
            new_name = c2.text_input("名稱 (例: 大東電)")
            new_cost = c3.number_input("成本", value=0.0, step=0.1)
            new_shares = c4.number_input("張數", value=1, min_value=1) * 1000
            
            if st.form_submit_button("執行存入"):
                if new_code and new_name:
                    st.session_state.portfolio.append({
                        "code": new_code, "name": new_name, "cost": new_cost, "shares": new_shares
                    })
                    st.success(f"✅ 已存入 {new_name} ({new_code})")
                    st.rerun() # 立即刷新顯示

    # 刪除與列表功能
    st.divider()
    st.subheader("📋 現有持股清單 (精益求精)")
    if st.session_state.portfolio:
        for idx, s in enumerate(st.session_state.portfolio):
            col1, col2, col3 = st.columns([5, 2, 1])
            col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']}")
            col2.write(f"持有股數: {s['shares']} ({int(s['shares']/1000)} 張)")
            if col3.button("🗑️ 刪除", key=f"del_{s['code']}_{idx}"):
                st.session_state.portfolio.pop(idx)
                st.rerun() # 立即刷新顯示
    else:
        st.info("目前庫存清空，準備下一次狙擊。")
