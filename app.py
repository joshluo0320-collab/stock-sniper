import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# ==========================================
# 0. 核心配置與金流初始化
# ==========================================
st.set_page_config(page_title="鷹眼戰術中心-金流版", page_icon="🦅", layout="wide")

# 初始化 Session (僅限您的瀏覽器使用)
if 'cash' not in st.session_state:
    st.session_state.cash = 300000.0  # 更新起始資金為 30 萬
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [{"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000}, {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}]
if 'history' not in st.session_state:
    st.session_state.history = [] # 儲存已實現損益紀錄

FEE_RATE = 0.001425  # 手續費 (預設無折扣)
TAX_RATE = 0.003     # 證交稅

with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v15.1")
    trade_mode = st.radio("⚔️ 選擇交易模式", ["右側順勢 (10D)", "左側逆勢 (22D)"])
    st.divider()
    # 金流看板
    st.metric("💰 現有可用資金", f"{st.session_state.cash:,.2f} 元")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理", "📑 歷史對帳單"])

# ==========================================
# 1. 庫存戰情：含手續費的精準損益
# ==========================================
if page == "📊 庫存戰情":
    st.header(f"📊 {trade_mode} - 即時損益監控")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                last_p = round(float(t.history(period="1d").iloc[-1]['Close']), 2)
                # 預估賣出淨額 (扣除手續費與稅)
                net_sell = (last_p * s['shares']) * (1 - FEE_RATE - TAX_RATE)
                pnl = net_sell - (s['cost'] * s['shares'] * (1 + FEE_RATE))
                with st.container(border=True):
                    st.subheader(f"{s['name']} ({s['code']})")
                    st.markdown(f"現價：**{last_p}**")
                    st.markdown(f"預估結算損益：<span style='color:{'red' if pnl >= 0 else 'green'}; font-weight:bold;'>{pnl:+, .2f}</span>", unsafe_allow_html=True)
            except: st.error(f"{s['code']} 讀取中...")

# ==========================================
# 2. 市場掃描：加入現有資金評比
# ==========================================
elif page == "🎯 市場掃描":
    st.header(f"🎯 {trade_mode} - 資金評比掃描")
    # ... (1064 支掃描邏輯略)
    if st.session_state.scan_results is not None:
        df = st.session_state.scan_results.copy()
        # 加入資金評比欄位 (買 1 張的門檻)
        df['資金評比'] = df.apply(lambda x: "✅ 可購入" if (x['收盤價'] * 1000 * (1 + FEE_RATE)) <= st.session_state.cash else "⚠️ 資金不足", axis=1)
        st.data_editor(df, hide_index=True)

# ==========================================
# 3. 庫存管理：賣出紀錄與資金回流
# ==========================================
elif page == "➕ 庫存管理":
    st.header("➕ 庫存與金流管理")
    # 賣出邏輯 (實體化)
    for idx, s in enumerate(st.session_state.portfolio):
        c1, c2, c3 = st.columns([4, 2, 1])
        c1.write(f"**{s['name']}** ({s['code']}) | 成本: {s['cost']}")
        sell_p = c2.number_input("賣出單價", key=f"sp_{idx}", value=s['cost'])
        if c3.button("執行賣出", key=f"btn_{idx}"):
            # 計算回流金流
            gross = sell_p * s['shares']
            net_return = gross * (1 - FEE_RATE - TAX_RATE)
            st.session_state.cash += net_return # 資金存回錢包
            # 存入對帳單
            profit = net_return - (s['cost'] * s['shares'] * (1 + FEE_RATE))
            st.session_state.history.append({"代號": s['code'], "名稱": s['name'], "獲利": round(profit, 2), "回流資金": round(net_return, 2)})
            st.session_state.portfolio.pop(idx)
            st.rerun()

elif page == "📑 歷史對帳單":
    st.header("📑 已實現損益紀錄")
    if st.session_state.history:
        st.table(pd.DataFrame(st.session_state.history))
    else: st.info("尚無結帳紀錄。")
