import streamlit as st

# ==========================================
# 0. 資金與庫存初始化 (Session State)
# ==========================================
if 'cash' not in st.session_state:
    st.session_state.cash = 300000.0  # 預設起始資金 30 萬
if 'history' not in st.session_state:
    st.session_state.history = [] # 賣出紀錄 (已實現損益)

# 手續費參數 (可依您的券商折扣調整)
FEE_RATE = 0.001425  # 手續費
TAX_RATE = 0.003     # 交易稅

with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v15.0")
    st.metric("💰 目前現有資金", f"{st.session_state.cash:,.0f} 元")
    
    # 金流手動校正 (例如入金/出金)
    new_cash = st.number_input("資金校正 (入金/出金)", value=0.0)
    if st.button("更新金流"):
        st.session_state.cash += new_cash
        st.rerun()

# ==========================================
# 1. 庫存管理：精準賣出與金流回收
# ==========================================
def sell_stock(idx, sell_price):
    s = st.session_state.portfolio[idx]
    # 計算賣出金流 (扣除手續費與稅)
    gross_amount = sell_price * s['shares']
    fee = gross_amount * FEE_RATE
    tax = gross_amount * TAX_RATE
    net_amount = gross_amount - fee - tax
    
    # 更新現有資金
    st.session_state.cash += net_amount
    
    # 記錄至已實現損益 (包含損益金額)
    profit = net_amount - (s['cost'] * s['shares'])
    st.session_state.history.append({
        "名稱": s['name'], "賣出價": sell_price, "獲利": profit, "回流資金": net_amount
    })
    
    # 從持股移除
    st.session_state.portfolio.pop(idx)
    st.rerun()

# ==========================================
# 2. 市場掃描：加入現有資金評比
# ==========================================
# 在顯示掃描結果時，新增一欄：
# df['資金評比'] = df.apply(lambda x: "✅ 可購入" if (x['收盤價'] * 1000 * 1.001425) <= st.session_state.cash else "⚠️ 資金不足", axis=1)
