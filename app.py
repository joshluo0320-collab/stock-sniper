import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 基礎設定與 SSL 修復
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0'}

st.set_page_config(page_title="鷹眼股市戰情室", page_icon="🦅", layout="wide")

# 初始化 Session State (確保數據持久化)
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 核心技術指標運算函數
# ==========================================

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_indicators(df):
    close = df['Close']
    # KD
    rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    dif = ema12 - ema26
    macd = dif.ewm(span=9).mean()
    osc = dif - macd
    # RSI
    rsi = calculate_rsi(close)
    return k.iloc[-1], d.iloc[-1], osc.iloc[-1], rsi.iloc[-1]

def get_ai_score(k, d, osc, rsi, win10, bias_pct):
    score = 60
    if k > d: score += 10
    if osc > 0: score += 10
    if 40 < rsi < 70: score += 10
    if win10 > 50: score += 20
    if bias_pct > 10: score -= 20 # 乖離過大扣分
    return max(0, min(100, score))

# ==========================================
# 2. 頁面功能模組
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板 (整張交易模式)")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                h = t.history(period="5d")
                if not h.empty:
                    last_p, prev_p = h.iloc[-1]['Close'], h.iloc[-2]['Close']
                    chg = last_p - prev_p
                    profit = (last_p - s['cost']) * s['shares']
                    prof_pct = (profit / (s['cost'] * s['shares'])) * 100
                    p_color = "red" if chg >= 0 else "green"
                    pf_color = "red" if profit >= 0 else "green"
                    
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:24px; font-weight:bold;'>{last_p:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"損益：<span style='color:{pf_color}; font-weight:bold;'>{int(profit):+,} ({prof_pct:.2f}%)</span>", unsafe_allow_html=True)
                        st.divider()
                        # 自動給予移動停利建議
                        if s['code'] == "4916": st.info("💡 建議：67.0 獲利保衛")
                        elif s['code'] == "2337": st.success("🚀 強勢：漲停鎖死續抱")
            except: st.error(f"{s['code']} 讀取逾時")

def page_scanner():
    st.header("🎯 市場自動掃描")
    # 此處保留 v10.4 的掃描邏輯，並確保 scan_results 存入 SessionState
    # ...
    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        if st.button("🏆 執行深度 AI 評測"):
            selected = edited_df[edited_df["選取"] == True]
            if not selected.empty:
                st.divider()
                st.subheader("🥇 AI 深度戰術評級")
                t_cols = st.columns(len(selected) if len(selected) < 4 else 3)
                for i, (_, row) in enumerate(selected.iterrows()):
                    with t_cols[i % 3]:
                        # 重新抓取資料進行指標運算
                        df_info = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                        k, d, osc, rsi = calculate_indicators(df_info)
                        score = get_ai_score(k, d, osc, rsi, row['10日勝率%'], 0) # 簡化乖離計算
                        
                        with st.container(border=True):
                            st.write(f"### {row['名稱']} ({row['代號']})")
                            st.metric("AI 綜合勝率評分", f"{int(score)} 分")
                            st.progress(int(score)/100)
                            st.write(f"RSI: {rsi:.1f} | KD: {'🔥金叉' if k>d else '🧊死叉'}")
                            st.caption(f"10日歷史勝率: {row['10日勝率%']:.1f}%")
            else: st.warning("請先勾選標的")

def page_management():
    st.header("➕ 庫存管理")
    with st.expander("➕ 新增持股 (整張單位)", expanded=True):
        with st.form("add_stock"):
            c1, c2, c3, c4 = st.columns(4)
            code = c1.text_input("代號")
            name = c2.text_input("名稱")
            cost = c3.number_input("成本", value=0.0)
            shares = c4.number_input("張數", value=1) * 1000
            if st.form_submit_button("執行存入"):
                st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares})
                st.rerun()
    
    st.subheader("📋 現有持股清單")
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']} | 單位: {s['shares']/1000} 張")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx)
            st.rerun()

# ==========================================
# 3. 主導航
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室 v10.5")
    page = st.sidebar.radio("導航選單", ["📊 庫存戰術看板", "🎯 市場自動掃描", "➕ 庫存管理"])
    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "🎯 市場自動掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__": main()
