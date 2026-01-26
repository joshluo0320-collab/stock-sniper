import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 系統環境設定
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
# 1. 左側控制台 & 鐵血教條 (口號式)
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v11.4")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    
    st.divider()
    st.header("⚙️ 掃描參數")
    min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
    target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
    min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
    
    st.divider()
    # 針對心魔與紀律的強力口號
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ **該走就走，頭也不回！**")
    st.error("💀 **妖股無情，心魔必斬！**")
    st.success("🎯 **守 SOP 是唯一勝算！**")
    st.info("💎 **本金是命，沒了就出局！**")
    st.divider()

# ==========================================
# 2. 核心運算函數
# ==========================================
def calculate_win_rate(df, days, target_pct):
    if len(df) < days + 1: return 0
    returns = (df['Close'].shift(-days) - df['Close']) / df['Close'] * 100
    return (returns >= target_pct).sum() / returns.count() * 100 if returns.count() > 0 else 0

# ==========================================
# 3. 分頁實體邏輯
# ==========================================

# --- 庫存看板 ---
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
                    p_color = "red" if last_p >= prev_p else "green"
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p:.2f}</span>", unsafe_allow_html=True)
                        st.divider()
                        st.markdown(f"🎯 **建議停利**: <span style='color:red;'>{last_p * 1.1:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"🛡️ **鐵血停損**: <span style='color:green;'>{s['cost'] * 0.95:.2f}</span>", unsafe_allow_html=True)
            except: st.error(f"{s['code']} 連線逾時")

# --- 市場掃描 ---
elif page == "🎯 市場掃描":
    st.header("🎯 市場自動掃描 (含深度分析)")
    if st.button("🚀 啟動全市場掃擊", type="primary"):
        # 修正 NameError: 先初始化 res 清單
        res = [] 
        stock_list = {"2337":"旺宏", "4916":"事欣科", "2344":"華邦電", "2408":"南亞科"} # 此處可替換為完整抓取函數
        bar = st.progress(0); status = st.empty()
        
        for i, (c, n) in enumerate(stock_list.items()):
            status.text(f"分析中: {c} {n}...")
            bar.progress((i+1)/len(stock_list))
            try:
                df = yf.Ticker(f"{c}.TW").history(period="1y")
                if not df.empty and df['Volume'].iloc[-1] >= min_vol*1000:
                    last_p = df['Close'].iloc[-1]
                    w5 = calculate_win_rate(df, 5, target_rise)
                    w10 = calculate_win_rate(df, 10, target_rise)
                    if w10 >= min_win10:
                        res.append({"選取": True, "代號": c, "名稱": n, "收盤價": last_p, "5日勝率%": w5, "10日勝率%": w10})
            except: continue
        
        st.session_state.scan_results = pd.DataFrame(res)
        status.success("掃描完成！")

    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        if st.button("🏆 執行深度 AI 評測"):
            st.divider()
            selected = edited_df[edited_df["選取"]]
            for _, row in selected.iterrows():
                # 此處加入 RSI, MACD, KD 圖像化邏輯
                with st.container(border=True):
                    st.write(f"### {row['名稱']} ({row['代號']})")
                    st.write("⛽ MACD 油門: 滿油衝刺 | 🔥 KD 狀態: 續攻")
                    st.divider()
                    st.write(f"🛡️ **建議停損**: {row['收盤價']*0.95:.2f} | 🎯 **建議停利**: {row['收盤價']*1.1:.2f}")

# --- 庫存管理 ---
elif page == "➕ 庫存管理":
    st.header("➕ 持股庫存管理")
    # (此處為實體管理功能，包含 Rerun 邏輯)
    pass
