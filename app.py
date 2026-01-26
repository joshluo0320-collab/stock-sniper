import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 系統與連線設定
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
# 1. 鐵血左側面板 (Sidebar)
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v11.3")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    
    st.divider()
    st.header("⚙️ 掃描參數")
    min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
    target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
    min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
    
    # --- 鐵血紀律教條 (口號化) ---
    st.divider()
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ **該走就走，頭也不回！**")
    st.success("🎯 **嚴守 SOP，唯快不破！**")
    st.info("💎 **本金是命，沒了就出局！**")
    st.error("💀 **妖股無情，心魔必斬！**")
    st.divider()

# ==========================================
# 2. 核心分析功能
# ==========================================
def analyze_deep(code):
    try:
        df = yf.Ticker(f"{code}.TW").history(period="1y")
        close = df['Close']
        # RSI
        delta = close.diff(); g = (delta.where(delta > 0, 0)).rolling(14).mean(); l = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = (100 - (100 / (1 + g/l))).iloc[-1]
        # MACD
        ema12 = close.ewm(span=12).mean(); ema26 = close.ewm(span=26).mean(); dif = ema12 - ema26; dea = dif.ewm(span=9).mean(); osc = dif - dea
        # KD
        rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean().iloc[-1]
        return rsi, osc.iloc[-1], k, close.iloc[-1]
    except: return None

# ==========================================
# 3. 分頁實體邏輯
# ==========================================

if page == "📊 庫存戰情":
    st.header("📊 即時損益監控")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            # ... (紅漲綠跌顯示代碼)
            with st.container(border=True):
                st.subheader(f"{s['name']} ({s['code']})")
                st.markdown(f"🎯 **目標停利**: <span style='color:red;'>{s['cost'] * 1.1:.2f}</span>", unsafe_allow_html=True)
                st.markdown(f"🛡️ **鐵血停損**: <span style='color:green;'>{s['cost'] * 0.95:.2f}</span>", unsafe_allow_html=True)

elif page == "🎯 市場掃描":
    st.header("🎯 全市場自動掃描評測")
    if st.button("🚀 啟動掃擊", type="primary"):
        # (掃描邏輯：計算 5日與 10日勝率)
        st.session_state.scan_results = pd.DataFrame(res)
        
    if st.session_state.scan_results is not None:
        st.subheader("📋 初步掃描結果 (含5日/10日勝率)")
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        
        if st.button("🏆 執行深度 AI 評測 (RSI/MACD/KD)"):
            st.divider()
            selected = edited_df[edited_df["選取"]]
            t_cols = st.columns(len(selected) if len(selected) < 4 else 3)
            for i, (_, row) in enumerate(selected.iterrows()):
                res = analyze_deep(row['代號'])
                if res:
                    rsi, osc, k, last_p = res
                    with t_cols[i % 3]:
                        with st.container(border=True):
                            st.write(f"### {row['名稱']} ({row['代號']})")
                            st.write(f"RSI 動能計")
                            st.progress(int(rsi)/100, text=f"{rsi:.1f}")
                            st.write(f"MACD 油門: {'⛽ 滿油衝刺' if osc > 0 else '🛑 減速待機'}")
                            st.write(f"KD 攻勢: {'🔥 續攻' if k > 50 else '🧊 整理'}")
                            st.divider()
                            st.markdown(f"🛡️ **停損防護**: {last_p*0.95:.2f} | 🎯 **停利點**: {last_p*1.1:.2f}")

elif page == "➕ 庫存管理":
    # ... (管理功能代碼：確保 Rerun 刪除順暢)
    pass
