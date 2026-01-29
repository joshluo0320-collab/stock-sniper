import streamlit as st
import yfinance as yf
import pandas as pd

# ==========================================
# 0. 核心配置與 30 萬金流初始化
# ==========================================
st.set_page_config(page_title="鷹眼資產戰情室 v16.4", page_icon="🦅", layout="wide")

if 'initial_cash' not in st.session_state:
    st.session_state.initial_cash = 300000.00
if 'current_cash' not in st.session_state:
    st.session_state.current_cash = 300000.00
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]

FEE_RATE = 0.001425
TAX_RATE = 0.003

# ==========================================
# 1. 資產總覽面板 (動態現價 + 現金)
# ==========================================
with st.sidebar:
    st.title("🦅 戰情中心 v16.4")
    page = st.radio("📡 系統導航", ["📈 資產總覽", "🎯 策略篩選", "➕ 庫存/金流管理"])
    st.divider()
    trade_mode = st.radio("⚔️ 戰術模式", ["右側順勢 (10D)", "左側逆勢 (縮時反轉)"])

if page == "📈 資產總覽":
    st.header("📈 實體資產累積面板")
    
    total_stock_mkt_val = 0.0
    stock_details = []
    
    for s in st.session_state.portfolio:
        try:
            t = yf.Ticker(f"{s['code']}.TW")
            hist = t.history(period="1d")
            last_p = round(float(hist['Close'].iloc[-1]), 2) if not hist.empty else s['cost']
            mkt_val = round(last_p * s['shares'], 2)
            total_stock_mkt_val += mkt_val
            
            # 精確損益計算
            net_profit = (mkt_val * (1-FEE_RATE-TAX_RATE)) - (s['cost'] * s['shares'] * (1+FEE_RATE))
            stock_details.append({
                "名稱": s['name'], "持股": s['shares'], "成本": f"{s['cost']:.2f}", 
                "現價": f"{last_p:.2f}", "市值": f"{mkt_val:,.2f}", "損益": f"{net_profit:+,.2f}"
            })
        except: continue

    # 總資產 = 現金 + 股票市值
    net_assets = round(st.session_state.current_cash + total_stock_mkt_val, 2)
    roi = round(((net_assets - st.session_state.initial_cash) / st.session_state.initial_cash) * 100, 2)

    c1, c2, c3 = st.columns(3)
    c1.metric("💰 總資產淨值", f"{net_assets:,.2f}", f"{roi:+.2f}%")
    c2.metric("💵 手頭可用現金", f"{st.session_state.current_cash:,.2f}")
    c3.metric("💹 持股總市值", f"{total_stock_mkt_val:,.2f}")
    
    if stock_details:
        st.table(pd.DataFrame(stock_details))

# ==========================================
# 2. 庫存/金流管理 (新增：直接刪除 vs. 手動賣出)
# ==========================================
elif page == "➕ 庫存/金流管理":
    st.header("➕ 庫存與金流管理")
    
    # --- 購入機制 ---
    with st.form("manual_buy"):
        st.subheader("🛒 新增持股 (自動扣除現金)")
        cols = st.columns(4)
        m_code = cols[0].text_input("代號")
        m_name = cols[1].text_input("名稱")
        m_cost = cols[2].number_input("購入單價", format="%.2f")
        m_shares = cols[3].number_input("股數", step=1000, value=1000)
        if st.form_submit_button("確認購入"):
            total_cost = round(m_cost * m_shares * (1 + FEE_RATE), 2)
            if total_cost <= st.session_state.current_cash:
                st.session_state.portfolio.append({"code": m_code, "name": m_name, "cost": m_cost, "shares": m_shares})
                st.session_state.current_cash -= total_cost
                st.rerun()
            else: st.error("可用現金不足")

    st.divider()
    
    # --- 庫存異動機制 (核心修復) ---
    st.subheader("🗑️ 庫存異動與結帳")
    for idx, s in enumerate(st.session_state.portfolio):
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            col1.write(f"**{s['name']}** ({s['code']}) \n 成本: {s['cost']:.2f} | 股數: {s['shares']}")
            
            # [功能 2] 手動輸入賣出金額
            actual_sell_price = col2.number_input(f"手動輸入賣出單價", key=f"sell_{idx}", format="%.2f", value=s['cost'])
            
            # 賣出結帳按鈕 (會回收資金)
            if col3.button("賣出結帳", key=f"btn_sell_{idx}"):
                gross = actual_sell_price * s['shares']
                net_return = round(gross * (1 - FEE_RATE - TAX_RATE), 2)
                st.session_state.current_cash += net_return
                st.session_state.portfolio.pop(idx)
                st.success(f"已結帳，回流現金: {net_return:,.2f}")
                st.rerun()
            
            # [功能 1] 直接刪除股票 (不列入資產/不回收資金)
            if col4.button("直接刪除", key=f"btn_del_{idx}", help="僅移除庫存，不影響現金餘額"):
                st.session_state.portfolio.pop(idx)
                st.warning(f"已直接刪除 {s['name']}，現金未變動。")
                st.rerun()

# (策略篩選頁面邏輯維持 v16.3 之嚴苛篩選架構，略)
