import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 系統與 SSL 設定
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

st.set_page_config(page_title="鷹眼戰術中心", page_icon="🦅", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 白話指標解釋邏輯
# ==========================================
def explain_rank(val):
    """位階解釋：這張票現在貴不貴？"""
    if val < 20: return f"{val:.1f}% (💎 底部區：打折沒人要，低風險)"
    if val < 50: return f"{val:.1f}% (📈 穩健區：剛發動，趨勢形成中)"
    if val < 80: return f"{val:.1f}% (🚀 衝刺區：熱度高，隨時回檔)"
    return f"{val:.1f}% (💀 超標區：正在登頂，摔下來最痛)"

def explain_rsi(val):
    """RSI 解釋：現在有多少人在搶？"""
    if val > 70: return f"{val:.1f} (🔥 瘋狂期：全民瘋搶，隨時力竭)"
    if val > 50: return f"{val:.1f} (🚀 動能期：有人追價，熱門標的)"
    if val > 30: return f"{val:.1f} (🧊 觀望期：熱度一般，沒人發現)"
    return f"{val:.1f} (🌑 冷清期：沒人要搶，市場冰點)"

# ==========================================
# 2. 鐵血左側面板
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v12.2")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ **該走就走，頭也不回！**")
    st.error("💀 **妖股無情，心魔必斬！**")
    st.success("🎯 **守 SOP 是唯一勝算！**")

# ==========================================
# 3. 分頁實體邏輯
# ==========================================

if page == "📊 庫存戰情":
    st.header("📊 即時損益監控 (精確顯示)")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                h = t.history(period="10d")
                if not h.empty:
                    last_p = round(h.iloc[-1]['Close'], 2)
                    prev_p = round(h.iloc[-2]['Close'], 2)
                    diff = round(last_p - s['cost'], 2)
                    total_pnl = round(diff * s['shares'], 2)
                    
                    p_color = "red" if last_p >= prev_p else "green"
                    pnl_color = "red" if total_pnl >= 0 else "green"
                    
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p}</span>", unsafe_allow_html=True)
                        st.markdown(f"單張損益：<span style='color:{pnl_color}; font-weight:bold;'>{total_pnl}</span>", unsafe_allow_html=True)
                        st.divider()
                        st.write(f"🛡️ **鐵血停損**: {round(s['cost'] * 0.95, 2)}")
                        st.write(f"🎯 **建議停利**: {round(s['cost'] * 1.1, 2)}")
            except: st.error(f"{s['code']} 讀取失敗")

elif page == "🎯 市場掃描":
    st.header("🎯 市場掃描與深度評測 (白話版)")
    # ... (掃描按鈕與 1064 支全樣本邏輯) ...
    
    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True)
        
        if st.button("🏆 執行深度 AI 表格評測"):
            deep_list = []
            for _, row in edited_df[edited_df["選取"]].iterrows():
                # (運算邏輯...)
                rank, rsi, osc = 41.1, 48.5, 0.5 # 範例數據
                last_p = round(row['收盤價'], 2)
                
                deep_list.append({
                    "名稱": row['名稱'], "代號": row['代號'], 
                    "10日勝率%": f"{row['10日勝率%']:.1f}%",
                    "位階(貴不貴)": explain_rank(rank),
                    "力道(熱不熱)": explain_rsi(rsi),
                    "油門(MACD)": "⛽ 滿油衝刺" if osc > 0 else "🛑 減速待機",
                    "建議進場": last_p,
                    "🛡️ 鐵血停損": round(last_p * 0.95, 2),
                    "🎯 目標停利": round(last_p * 1.1, 2)
                })
            st.table(pd.DataFrame(deep_list).sort_values(by="10日勝率%", ascending=False))

elif page == "➕ 庫存管理":
    # ... (管理功能邏輯) ...
    pass
