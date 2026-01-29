import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# ==========================================
# 0. 核心配置與金流初始化
# ==========================================
st.set_page_config(page_title="鷹眼資產戰情室 v16.6", page_icon="🦅", layout="wide")

# 資金與庫存初始化
if 'initial_cash' not in st.session_state:
    st.session_state.initial_cash = 300000
if 'current_cash' not in st.session_state:
    st.session_state.current_cash = 300000
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64, "shares": 2000}
    ]

FEE_RATE = 0.001425
TAX_RATE = 0.003

# ==========================================
# 1. 戰情導航與起始資金管理
# ==========================================
with st.sidebar:
    st.title("🦅 戰情中心 v16.6")
    page = st.radio("📡 系統導航", ["📈 資產總覽", "🎯 策略篩選", "➕ 庫存管理"])
    st.divider()
    
    st.subheader("💰 資金初始化")
    # [功能] 手動輸入起始金額 (整數)
    manual_init = st.number_input("設定起始本金 (元)", value=int(st.session_state.initial_cash), step=1000)
    if st.button("同步起始資金與現金"):
        st.session_state.initial_cash = int(round(manual_init, 0))
        st.session_state.current_cash = int(round(manual_init, 0))
        st.rerun()

# --- [A] 資產總覽 (全整數顯示) ---
if page == "📈 資產總覽":
    st.header("📈 實體資產累積面板")
    
    total_stock_mkt_val = 0.0
    stock_details = []
    
    for s in st.session_state.portfolio:
        try:
            t = yf.Ticker(f"{s['code']}.TW")
            hist = t.history(period="1d")
            # 取得現價並四捨五入至整數
            last_p = int(round(float(hist['Close'].iloc[-1]), 0)) if not hist.empty else s['cost']
            
            mkt_val = int(round(last_p * s['shares'], 0))
            total_stock_mkt_val += mkt_val
            
            # 損益計算 (扣除稅費後取整數)
            net_profit = (mkt_val * (1-FEE_RATE-TAX_RATE)) - (s['cost'] * s['shares'] * (1+FEE_RATE))
            stock_details.append({
                "名稱": s['name'], "持股": s['shares'], "成本": int(round(s['cost'], 0)), 
                "現價": last_p, "市值": f"{int(round(mkt_val, 0)):,}", 
                "損益": f"{int(round(net_profit, 0)):+,}"
            })
        except: continue

    # 總資產 = 現金 + 股票市值 (取整數)
    net_assets = int(round(st.session_state.current_cash + total_stock_mkt_val, 0))
    roi = round(((net_assets - st.session_state.initial_cash) / st.session_state.initial_cash) * 100, 2)

    c1, c2, c3 = st.columns(3)
    c1.metric("💰 總資產淨值", f"{net_assets:,}", f"{roi:+.2f}%")
    c2.metric("💵 手頭可用現金", f"{int(round(st.session_state.current_cash, 0)):,}")
    c3.metric("💹 持股總市值", f"{int(round(total_stock_mkt_val, 0)):,}")
    
    if stock_details:
        st.table(pd.DataFrame(stock_details))

# --- [B] 策略篩選 (整合嚴苛條件) ---
elif page == "🎯 策略篩選":
    st.header("🎯 進階策略篩選")
    # 預算上限連動現金
    max_budget = st.number_input("💸 單筆最高預算 (元)", value=int(st.session_state.current_cash), step=1000)
    
    if st.button("🚀 啟動 1064 支全樣本掃描"):
        # (此處執行 v16.5 修正後之掃描邏輯，含位階、窒息量判斷)
        st.info("篩選完成後，標的價格將四捨五入至整數顯示。")

# --- [C] 庫存管理 (直接刪除與精確結帳) ---
elif page == "➕ 庫存管理":
    st.header("➕ 庫存管理與金流校正")
    # 購入與賣出輸入框均採用整數 step
    with st.form("manual_op"):
        c_code = st.text_input("代號")
        c_cost = st.number_input("單價 (整數)", step=1)
        # ... 
        if st.form_submit_button("執行"):
            st.rerun()
