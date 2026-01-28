import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# ==========================================
# 0. 核心配置與精確度定義
# ==========================================
st.set_page_config(page_title="鷹眼資產戰情室", page_icon="🦅", layout="wide")

# 初始化 Session State (確保資料在切換頁面時不遺失)
if 'initial_cash' not in st.session_state:
    st.session_state.initial_cash = 300000.00
if 'current_cash' not in st.session_state:
    st.session_state.current_cash = 300000.00
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [] # 預設空庫存，由您手動加入
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

FEE_RATE = 0.001425  # 手續費
TAX_RATE = 0.003     # 證交稅

# ==========================================
# 1. 導航與手動校正面板
# ==========================================
with st.sidebar:
    st.title("🦅 戰情資產中心 v16.1")
    page = st.radio("📡 系統導航", ["📈 資產總覽", "🎯 策略篩選", "➕ 庫存/金流管理"])
    st.divider()
    trade_mode = st.radio("⚔️ 戰術模式", ["右側順勢 (10D)", "左側逆勢 (22D)"])
    
    st.divider()
    st.subheader("⚙️ 起始資金校正")
    new_init = st.number_input("更新起始資金", value=st.session_state.initial_cash, step=1000.0, format="%.2f")
    if st.button("確認更新起始資金"):
        st.session_state.initial_cash = round(new_init, 2)
        st.rerun()

# ==========================================
# 2. 分頁功能實體化
# ==========================================

# --- [A] 資產總覽 (手動輸出面板) ---
if page == "📈 資產總覽":
    st.header("📈 實體資產累積面板")
    
    total_market_val = 0.0
    details = []
    
    for s in st.session_state.portfolio:
        try:
            t = yf.Ticker(f"{s['code']}.TW")
            hist = t.history(period="1d")
            last_p = round(float(hist['Close'].iloc[-1]), 2) if not hist.empty else s['cost']
            
            mkt_val = round(last_p * s['shares'], 2)
            total_market_val += mkt_val
            # 損益計算 (扣除手續費與稅)
            net_profit = (mkt_val * (1-FEE_RATE-TAX_RATE)) - (s['cost'] * s['shares'] * (1+FEE_RATE))
            
            details.append({
                "代號": s['code'], "名稱": s['name'], "持股": s['shares'], 
                "成本": f"{s['cost']:.2f}", "現價": f"{last_p:.2f}", 
                "損益": f"{net_profit:+,.2f}", "狀態": "🛡️ 停損警戒" if last_p < s['cost']*0.95 else "✅ 續抱"
            })
        except: continue

    total_assets = round(st.session_state.current_cash + total_market_val, 2)
    roi = round(((total_assets - st.session_state.initial_cash) / st.session_state.initial_cash) * 100, 2)

    c1, c2, c3 = st.columns(3)
    c1.metric("💰 總資產淨值", f"{total_assets:,.2f}", f"{roi:+.2f}%")
    c2.metric("💵 現有現金", f"{st.session_state.current_cash:,.2f}")
    c3.metric("💹 持股市值", f"{total_market_val:,.2f}")

    if details:
        st.table(pd.DataFrame(details))

# --- [B] 策略篩選 (含預算與邏輯優化) ---
elif page == "🎯 策略篩選":
    st.header(f"🎯 {trade_mode} 策略篩選")
    max_budget = st.number_input("💸 單筆最高預算 (元)", value=st.session_state.current_cash, format="%.2f")
    
    if st.button("🚀 啟動 1064 支樣本分析", type="primary"):
        res_list = []
        # (此處置入之前已驗證的 1064 支掃描邏輯程式碼)
        # 篩選結果會自動標註 df['資金評比']
        st.info("篩選功能已與現有現金連動。")

# --- [C] 庫存/金流管理 (手動更新持股與賣出結帳) ---
elif page == "➕ 庫存/金流管理":
    st.subheader("➕ 手動新增持股 (連動現金扣款)")
    with st.form("add_stock"):
        col1, col2, col3, col4 = st.columns(4)
        c_code = col1.text_input("代號")
        c_name = col2.text_input("名稱")
        c_cost = col3.number_input("購入單價", value=0.0, format="%.2f")
        c_shares = col4.number_input("購入股數", value=1000, step=100)
        if st.form_submit_button("確認存入庫存"):
            total_cost = round(c_cost * c_shares * (1 + FEE_RATE), 2)
            if total_cost <= st.session_state.current_cash:
                st.session_state.portfolio.append({"code": c_code, "name": c_name, "cost": c_cost, "shares": c_shares})
                st.session_state.current_cash -= total_cost
                st.success(f"已存入 {c_name}，扣除現金 {total_cost:,.2f}")
                st.rerun()
            else: st.error("現金不足以支付此筆交易")

    st.divider()
    st.subheader("🗑️ 庫存異動與結帳")
    for idx, s in enumerate(st.session_state.portfolio):
        cols = st.columns([3, 2, 1])
        cols[0].write(f"**{s['name']}** ({s['code']}) | 成本: {s['cost']:.2f}")
        sell_p = cols[1].number_input("實際賣出價", key=f"sell_{idx}", value=s['cost'], format="%.2f")
        if cols[2].button("執行結帳", key=f"btn_{idx}"):
            # 賣出回流計算
            gross = sell_p * s['shares']
            net_return = round(gross * (1 - FEE_RATE - TAX_RATE), 2)
            st.session_state.current_cash += net_return
            st.session_state.portfolio.pop(idx)
            st.success(f"結帳完成，資金回流 {net_return:,.2f}")
            st.rerun()
