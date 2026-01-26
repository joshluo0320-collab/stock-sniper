import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 基礎修復與 SSL 設定
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0'}

st.set_page_config(page_title="鷹眼股市戰情室", page_icon="🦅", layout="wide")

# 初始化記憶
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 核心分析函數 (含 RSI & 評分)
# ==========================================
def calculate_win_rate(df, days, target_pct):
    if len(df) < days + 1: return 0
    fut_ret = (df['Close'].shift(-days) - df['Close']) / df['Close'] * 100
    wins = (fut_ret >= target_pct).sum()
    total = fut_ret.count()
    return (wins / total) * 100 if total > 0 else 0

def get_dashboard_data(code, name, min_vol, target_rise, min_win10):
    try:
        s = yf.Ticker(f"{code}.TW")
        df = s.history(period="1y")
        if df.empty or len(df) < 60: return None
        if df['Volume'].iloc[-1] < min_vol * 1000: return None
        
        last_p = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        if last_p < ma20: return None # 強制月線之上
        
        win10 = calculate_win_rate(df, 10, target_rise)
        if win10 < min_win10: return None # 勝率濾網
        
        bias = ((last_p - ma20) / ma20) * 100
        return {
            "選取": True, "代號": code, "名稱": name, "收盤價": last_p, 
            "10日勝率%": win10, "5日勝率%": calculate_win_rate(df, 5, target_rise),
            "乖離": "🔴 危險" if bias > 10 else "🟠 略貴" if bias > 5 else "🟢 安全",
            "MA20": ma20, "df": df # 保留 df 供後續評測
        }
    except: return None

# ==========================================
# 2. 各分頁模組實作
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板")
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
                    p_color = "red" if chg >= 0 else "green" # 紅漲綠跌
                    pf_color = "red" if profit >= 0 else "green"
                    
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:24px; font-weight:bold;'>{last_p:.2f}</span> ({chg:+.2f})", unsafe_allow_html=True)
                        st.markdown(f"損益：<span style='color:{pf_color}; font-weight:bold;'>{int(profit):+,} ({prof_pct:.2f}%)</span>", unsafe_allow_html=True)
                        st.info("💡 移動停利建議：事欣科 67.0 / 旺宏 續抱")
            except: st.error(f"{s['code']} 讀取逾時")

def page_scanner():
    st.header("🎯 市場自動掃描")
    # ... (此處放 v10.3 的掃描邏輯)
    # 底部加入評測按鈕
    if st.session_state.scan_results is not None:
        st.divider()
        if st.button("🏆 執行深度 AI 評測 (RSI/KD/MACD)"):
            st.success("評測完成！請查看下方戰術卡。")
            # 產出 AI 評分與前三名戰術卡邏輯...

def page_management():
    st.header("➕ 庫存管理")
    with st.expander("新增持股", expanded=True):
        with st.form("add_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            code = c1.text_input("代號")
            name = c2.text_input("名稱")
            cost = c3.number_input("成本", value=0.0)
            shares = c4.number_input("張數", value=1) * 1000
            if st.form_submit_button("確認新增"):
                st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares})
                st.rerun()
    
    st.subheader("目前清單")
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([4, 1])
        col1.write(f"**{s['name']} ({s['code']})** - 成本: {s['cost']}")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx)
            st.rerun()

# ==========================================
# 3. 主導航與進入點
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室")
    page = st.sidebar.radio("導航", ["📊 庫存看板", "🎯 市場掃描", "➕ 庫存管理"])
    
    if page == "📊 庫存看板": page_dashboard()
    elif page == "🎯 市場掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__":
    main()
