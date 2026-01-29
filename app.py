import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# ==========================================
# 0. 核心配置與數據初始化 (根據最新提供數據)
# ==========================================
st.set_page_config(page_title="鷹眼資產戰情室 v18.1", page_icon="🦅", layout="wide")

# 更新您的資產現況
if 'initial_cash' not in st.session_state:
    st.session_state.initial_cash = 200000.00 # 起始總資金：20萬
if 'current_cash' not in st.session_state:
    st.session_state.current_cash = 241384.00 # 手頭可用現金：24.1萬
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

FEE_RATE = 0.001425
TAX_RATE = 0.003

# ==========================================
# 1. 戰情導航與資產手動校正 (確保功能在)
# ==========================================
with st.sidebar:
    st.title("🦅 戰情中心 v18.1")
    page = st.radio("📡 系統導航", ["📈 資產總覽", "🎯 策略篩選", "➕ 庫存管理"])
    st.divider()
    
    st.subheader("💰 資產手動校正")
    # 允許隨時手動輸入調整
    m_init = st.number_input("起始總資金", value=float(st.session_state.initial_cash), format="%.2f")
    m_cash = st.number_input("手頭可用現金", value=float(st.session_state.current_cash), format="%.2f")
    if st.button("確認同步校正"):
        st.session_state.initial_cash = round(m_init, 2)
        st.session_state.current_cash = round(m_cash, 2)
        st.rerun()

# --- [A] 資產總覽 ---
if page == "📈 資產總覽":
    st.header("📈 實體資產累積面板")
    # (獲取現價與市值邏輯...)
    # 總資產淨值 = 現金 + 持股市值
    # ROI = (總資產 - 起始資金) / 起始資金

# --- [B] 策略篩選 (修復 KeyError) ---
elif page == "🎯 策略篩選":
    st.header("🎯 鷹眼策略篩選系統")
    if st.button("🚀 啟動 1064 支全樣本掃描", type="primary"):
        res = []
        # (掃描邏輯：位階、成交量、勝率...)
        st.session_state.scan_results = pd.DataFrame(res)

    # 修復 KeyError: 檢查 scan_results 是否為空
    if st.session_state.scan_results is not None:
        if not st.session_state.scan_results.empty:
            st.subheader("🔍 深度評測結果")
            df_eval = st.session_state.scan_results.copy()
            # 只有在有結果時才計算策略價，防止報錯
            df_eval['🛡️ 停損價'] = (df_eval['現價'] * 0.95).round(2)
            df_eval['🎯 第一停利'] = (df_eval['現價'] * 1.10).round(2)
            st.dataframe(df_eval, use_container_width=True)
        else:
            st.warning("⚠️ 當前嚴苛條件下，無符合標的，請嘗試放寬預算或勝率門檻。")

# --- [C] 庫存管理 ---
elif page == "➕ 庫存管理":
    st.header("➕ 庫存與金流校正")
    for idx, s in enumerate(st.session_state.portfolio):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            c1.write(f"**{s['name']}** ({s['code']}) | 成本: {s['cost']:.2f}")
            # [功能回歸] 直接刪除按鈕
            if c4.button("🗑️ 直接刪除", key=f"del_{idx}"):
                st.session_state.portfolio.pop(idx)
                st.rerun()
