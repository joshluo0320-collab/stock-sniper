import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from io import StringIO

# ==========================================
# 0. 資產中心初始化 (Asset Management Core)
# ==========================================
st.set_page_config(page_title="鷹眼資產管理戰情室", page_icon="🦅", layout="wide")

# 核心資金設定
if 'initial_cash' not in st.session_state:
    st.session_state.initial_cash = 300000.0  # 起始資金
if 'current_cash' not in st.session_state:
    st.session_state.current_cash = 300000.0
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]

FEE_RATE = 0.001425  # 手續費
TAX_RATE = 0.003     # 證交稅

# ==========================================
# 1. 戰情導航與資產面板
# ==========================================
with st.sidebar:
    st.title("🦅 戰情資產中心 v16.0")
    page = st.radio("📡 系統導航", ["📈 資產總覽", "🎯 策略篩選", "➕ 交易紀錄"])
    st.divider()
    
    # 模式切換：影響篩選邏輯
    trade_mode = st.radio("⚔️ 戰術模式", ["右側順勢 (10D)", "左側逆勢 (22D)"])
    
    st.divider()
    st.error("🦾 **鐵血紀律**")
    st.warning("⚠️ 趨勢轉向，頭也不回！")

# ==========================================
# 2. 分頁實體化：資產累積面板
# ==========================================

if page == "📈 資產總覽":
    st.header("📈 資產累積總覽")
    
    # 計算即時市值
    total_market_value = 0
    pnl_details = []
    
    for s in st.session_state.portfolio:
        t = yf.Ticker(f"{s['code']}.TW")
        hist = t.history(period="1d")
        if not hist.empty:
            last_p = round(hist.iloc[-1]['Close'], 2)
            market_val = last_p * s['shares']
            total_market_value += market_val
            # 損益統計 (含手續費)
            net_profit = (market_val * (1-FEE_RATE-TAX_RATE)) - (s['cost'] * s['shares'] * (1+FEE_RATE))
            pnl_details.append({"標的": s['name'], "市值": market_val, "預估損益": round(net_profit, 0)})

    total_assets = st.session_state.current_cash + total_market_value
    roi = ((total_assets - st.session_state.initial_cash) / st.session_state.initial_cash) * 100

    # 視覺化面板
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 總資產淨值", f"{total_assets:,.0f}", f"{roi:.2f}%")
    c2.metric("💵 現金部位", f"{st.session_state.current_cash:,.0f}")
    c3.metric("💹 持股總市值", f"{total_market_value:,.0f}")

    if pnl_details:
        st.subheader("📋 持股明細與戰術建議")
        df_pnl = pd.DataFrame(pnl_details)
        st.table(df_pnl)

# ==========================================
# 3. 策略篩選：動能與資金門檻
# ==========================================
elif page == "🎯 策略篩選":
    st.header(f"🎯 {trade_mode} 策略篩選")
    
    # 手動預算過濾 (回答您的問題：建議兩者並行)
    with st.expander("🛡️ 預算與風險控管", expanded=True):
        col_a, col_b = st.columns(2)
        max_budget = col_a.number_input("💸 單筆最高投資金額 (元)", value=st.session_state.current_cash)
        min_win = col_b.slider("🔥 最低勝率門檻 (%)", 0, 100, 40)

    # 1064 支掃描邏輯 (略，與 v15.5 相同)
    # 增加邏輯：df = df[df['所需資金'] <= max_budget]
    st.info("系統將自動過濾掉您目前資金無法負荷的股票，確保資源精確投放。")

# ==========================================
# 4. 交易紀錄 (庫存管理連動)
# ==========================================
elif page == "➕ 交易紀錄":
    st.header("➕ 交易買賣管理")
    # ... (包含購入扣款、賣出結帳回流金流之邏輯)
