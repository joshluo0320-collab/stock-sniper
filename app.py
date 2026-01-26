import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from io import StringIO

# ==========================================
# 0. 核心配置與快取修復
# ==========================================
st.set_page_config(page_title="鷹眼戰術中心", page_icon="🦅", layout="wide")

# 初始化：這部分代碼若傳給別人，他們會看到初始值，但後續操作不共通
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 鐵血導航面板 (紀律口號)
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v13.1")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ **該走就走，頭也不回！**")
    st.error("💀 **妖股無情，心魔必斬！**")
    st.success("🎯 **守 SOP 是唯一勝算！**")

# ==========================================
# 2. 庫存戰情 (精確損益 + 小數點修復)
# ==========================================
if page == "📊 庫存戰情":
    st.header("📊 持股監控 (損益倍數已修正)")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                h = t.history(period="5d")
                if not h.empty:
                    last_p = round(float(h.iloc[-1]['Close']), 2)
                    # 損益公式：(現價 - 成本) * 總股數
                    total_pnl = round((last_p - s['cost']) * s['shares'], 2)
                    p_color = "red" if last_p >= h.iloc[-2]['Close'] else "green"
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p}</span>", unsafe_allow_html=True)
                        st.markdown(f"總損益：<span style='color:{'red' if total_pnl >= 0 else 'green'}; font-weight:bold;'>{total_pnl:+,}</span>", unsafe_allow_html=True)
                        st.write(f"持有：{int(s['shares']/1000)} 張")
            except: st.error(f"{s['code']} 讀取失敗")

# ==========================================
# 3. 市場掃描 (1064 支全樣本 + 實體按鈕修復)
# ==========================================
elif page == "🎯 市場掃描":
    st.header("🎯 全市場 1000+ 樣本自動掃描")
    
    # 參數放在 Sidebar
    with st.sidebar:
        st.divider()
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
        min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)

    if st.button("🚀 啟動掃描", type="primary"):
        res_list = []
        try:
            # 獲取 1064 支清單
            url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            df_list = pd.read_html(requests.get(url, verify=False, timeout=10).text)[0]
            df_list.columns = df_list.iloc[0]
            stock_map = {p[0].strip(): p[1].strip() for p in (i.split('\u3000') for i in df_list.iloc[1:][df_list['CFICode'] == 'ESVUFR']['有價證券代號及名稱']) if len(p[0].strip()) == 4}
            
            bar = st.progress(0); status = st.empty(); total = len(stock_map)
            for i, (c, n) in enumerate(stock_map.items()):
                status.text(f"分析中 ({i+1}/{total}): {n} ({c})...")
                bar.progress((i+1)/total)
                try:
                    df = yf.Ticker(f"{c}.TW").history(period="1y")
                    if not df.empty and df['Volume'].iloc[-1] >= min_vol*1000:
                        ret10 = (df['Close'].shift(-10) - df['Close']) / df['Close'] * 100
                        w10 = (ret10 >= target_rise).sum() / ret10.count() * 100
                        if w10 >= min_win10:
                            res_list.append({"選取": True, "代號": c, "名稱": n, "收盤價": round(df['Close'].iloc[-1], 2), "10日勝率%": round(w10, 2)})
                except: continue
            st.session_state.scan_results = pd.DataFrame(res_list)
            status.success(f"完成！找到 {len(res_list)} 檔。")
        except Exception as e:
            st.error(f"連線失敗：{e}")

    if st.session_state.scan_results is not None:
        st.subheader("📋 深度決策表格")
        st.data_editor(st.session_state.scan_results, hide_index=True)
