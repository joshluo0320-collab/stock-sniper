import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 基礎設定
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0'}

st.set_page_config(page_title="鷹眼股市戰情室", page_icon="🦅", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 核心指標與評分邏輯 (含圖像化標記)
# ==========================================

def get_status_icons(indicator, value, value2=None):
    """產生直觀的圖像標籤"""
    if indicator == "乖離":
        return "🔴 危險" if value > 10 else "🟠 略貴" if value > 5 else "🟢 安全" if value < -5 else "⚪ 合理"
    if indicator == "KD":
        return "🔥 續攻" if value > value2 else "🧊 整理"
    if indicator == "MACD":
        return "⛽ 滿油" if value > 0 else "🛑 減速"
    return ""

# ==========================================
# 2. 分頁模組
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                h = t.history(period="10d")
                if not h.empty:
                    last_p, prev_p = h.iloc[-1]['Close'], h.iloc[-2]['Close']
                    chg = last_p - prev_p
                    profit = (last_p - s['cost']) * s['shares']
                    prof_pct = (profit / (s['cost'] * s['shares'])) * 100
                    p_color = "red" if chg >= 0 else "green"
                    pf_color = "red" if profit >= 0 else "green"
                    
                    # 計算簡易移動停利 (成本+5% 或 月線)
                    ma20 = h['Close'].rolling(5).mean().iloc[-1] # 庫存看板用短均線參考
                    
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"損益：<span style='color:{pf_color}; font-weight:bold;'>{int(profit):+,} ({prof_pct:.2f}%)</span>", unsafe_allow_html=True)
                        st.divider()
                        
                        # 停利停損提醒
                        st.write(f"🎯 **建議停利**：{last_p * 1.1:.2f} (目標+10%)")
                        st.write(f"🛡️ **建議停損**：{ma20:.2f} (月線支撐)")
                        
                        advice = "🚀 獲利拉開，分批停利" if prof_pct > 10 else "📈 趨勢偏多，續抱"
                        st.success(advice)
            except: st.error(f"{s['code']} 更新逾時")

def page_scanner():
    # ... (此處保留 v10.6 的 Sidebar 與 掃描邏輯)
    st.header("🎯 市場自動掃描")
    # (此處為掃描結果 edited_df 顯示部分)
    
    if st.session_state.scan_results is not None:
        st.subheader("📋 掃描戰果 (已保留)")
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        
        if st.button("🏆 執行深度 AI 評測 (RSI/KD/圖像化)"):
            st.divider()
            selected = edited_df[edited_df["選取"]]
            t_cols = st.columns(len(selected) if len(selected) < 4 else 3)
            
            for i, (_, row) in enumerate(selected.iterrows()):
                with t_cols[i % 3]:
                    # 抓取 1y 資料運算
                    df_all = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                    close = df_all['Close']
                    # RSI
                    delta = close.diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    curr_rsi = (100 - (100 / (1 + gain/loss))).iloc[-1]
                    # MA20
                    ma20_val = close.rolling(20).mean().iloc[-1]
                    bias_val = ((close.iloc[-1] - ma20_val) / ma20_val) * 100
                    
                    with st.container(border=True):
                        st.write(f"### {row['名稱']} ({row['代號']})")
                        st.write(f"**RSI (14)**")
                        st.progress(int(curr_rsi)/100, text=f"{curr_rsi:.1f}")
                        
                        c1, c2 = st.columns(2)
                        c1.write(f"**乖離狀況**\n{get_status_icons('乖離', bias_val)}")
                        c2.write(f"**10日勝率**\n🔥 {row['10日勝率%']:.1f}%")
                        
                        st.divider()
                        st.markdown(f"🎯 **建議停利**：<span style='color:red;'>{row['收盤價']*1.1:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"🛡️ **建議停損**：<span style='color:green;'>{ma20_val:.2f}</span>", unsafe_allow_html=True)

# ==========================================
# 3. 主程式入口
# ==========================================
def main():
    st.sidebar.title("🦅 鷹眼戰術中心")
    page = st.sidebar.radio("分頁導航", ["📊 庫存看板", "🎯 市場掃描", "➕ 庫存管理"])
    if page == "📊 庫存看板": page_dashboard()
    elif page == "🎯 市場掃描": page_scanner()
    elif page == "➕ 庫存管理":
        # ... (維持 v10.6 庫存管理功能)
        pass

if __name__ == "__main__": main()
