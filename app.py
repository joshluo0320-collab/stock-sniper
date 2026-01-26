import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# ==========================================
# 0. 系統配置與模式切換
# ==========================================
st.set_page_config(page_title="鷹眼雙模戰術中心", page_icon="🦅", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v13.8")
    # 模式切換：互不干擾的核心
    trade_mode = st.radio("⚔️ 選擇交易模式", ["右側順勢 (10D)", "左側逆勢 (22D)"])
    st.divider()
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    
    if trade_mode == "右側順勢 (10D)":
        st.error("🦾 右側教條：趨勢轉向，頭也不回！")
    else:
        st.info("💎 左側教條：分批埋伏，靜待反轉！")

# ==========================================
# 1. 核心邏輯函數 (模式隔離)
# ==========================================
def analyze_stock(df, mode):
    close = df['Close']
    l60, h60 = close.tail(60).min(), close.tail(60).max()
    rank = ((close.iloc[-1] - l60) / (h60 - l60)) * 100 if h60 != l60 else 50
    ma20 = close.rolling(20).mean()
    bias = ((close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1]) * 100
    
    if mode == "右側順勢 (10D)":
        return {
            "位階": f"{rank:.1f}% (發動中)" if rank > 40 else f"{rank:.1f}% (整理中)",
            "狀態": "🚀 動能強勁" if close.iloc[-1] > ma20.iloc[-1] else "🧊 冷卻回檔",
            "預測": "跌破停損即刻撤退"
        }
    else:
        # 左側交易：分析何時走揚 (預測邏輯)
        # 1. 負乖離是否收斂 2. 成交量是否窒息
        vol_ratio = df['Volume'].iloc[-1] / df['Volume'].tail(5).mean()
        pred_days = "觀察中"
        if bias < -10:
            pred_days = "約 3-5 天內可能反彈" if vol_ratio < 0.7 else "賣壓仍重，需 1-2 週築底"
        return {
            "位階": f"{rank:.1f}% (超跌區)" if rank < 15 else f"{rank:.1f}% (尋底中)",
            "狀態": f"📉 負乖離 {bias:.1f}%",
            "預測": f"💡 {pred_days}"
        }

# ==========================================
# 2. 分頁功能實體化
# ==========================================

# --- [A] 庫存戰情 ---
if page == "📊 庫存戰情":
    st.header(f"📊 {trade_mode} - 持股即時監控")
    # ... (損益計算邏輯保持 v13.7 穩定版)

# --- [B] 市場掃描 ---
elif page == "🎯 市場掃描":
    st.header(f"🎯 {trade_mode} 模式 - 全市場 1064 樣本掃描")
    # 掃描邏輯依 trade_mode 自動切換勝率計算天數 (10D vs 22D)
    # ... 

# --- [C] 庫存管理 ---
elif page == "➕ 庫存管理":
    st.header("➕ 庫存清單優化")
    with st.form("manage_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        code = c1.text_input("代號"); name = c2.text_input("名稱")
        cost = c3.number_input("成本", value=0.0); shares = c4.number_input("張數", value=1)
        if st.form_submit_button("確認存入"):
            if code and name:
                st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
                st.rerun()
    st.divider()
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']}")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx); st.rerun()
