import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 基礎修復與設定
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0'}

st.set_page_config(page_title="鷹眼股市戰情室", page_icon="🦅", layout="wide")

# 初始化庫存記憶
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]

# 初始化掃描記憶
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 核心函數 (保留原有高精準邏輯)
# ==========================================

@st.cache_data(ttl=3600*24)
def get_all_tw_stocks_map():
    stock_map = {}
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        response = requests.get(url, verify=False)
        response.encoding = 'big5'
        df = pd.read_html(StringIO(response.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df = df[df['CFICode'] == 'ESVUFR']
        for item in df['有價證券代號及名稱']:
            parts = item.split('\u3000')
            if len(parts) >= 2:
                code, name = parts[0].strip(), parts[1].strip()
                if len(code) == 4: stock_map[code] = name
    except: return {"2330": "台積電"}
    return stock_map

# ... (其餘計算函數 calculate_win_rate, get_dashboard_data, calculate_sniper_score 維持 v10.1)

# ==========================================
# 2. 頁面模組
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板")
    # 此處會自動顯示紅漲綠跌邏輯
    # (代碼同 v10.1)
    pass

def page_scanner():
    st.header("🎯 全市場自動掃描")
    stock_map = get_all_tw_stocks_map()
    all_codes = list(stock_map.keys())
    
    with st.sidebar:
        st.header("⚙️ 戰術控制台")
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000, step=100)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 20, 10)
        min_win_rate = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
        st.success("✅ 強制開啟：股價 > 月線 (MA20)")

    if st.button("🚀 啟動全市場掃描", type="primary"):
        # 掃描邏輯...
        pass

    # 顯示搜尋結果並提供「深入評測」按鈕
    if st.session_state.scan_results is not None:
        st.subheader("📋 掃描戰果 (已保留)")
        edited_df = st.data_editor(
            st.session_state.scan_results,
            key="scanner_editor", # 固定Key以維持狀態
            column_config={"選取": st.column_config.CheckboxColumn(default=True)},
            hide_index=True, use_container_width=True
        )

        if st.button("🏆 對選中股票進行深入 AI 評測"):
            final_df = edited_df[edited_df["選取"] == True].copy()
            if not final_df.empty:
                st.subheader("🥇 AI 評測戰術卡")
                # 此處執行 calculate_sniper_score 並顯示前三名卡片
                # 即使只有兩張也會進行完整分析
            else:
                st.error("請至少勾選一檔股票進行評測")

def page_management():
    st.header("➕ 庫存管理")
    
    # --- 新增功能 ---
    with st.expander("➕ 新增持股", expanded=True):
        with st.form("add_stock_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            new_code = c1.text_input("代號")
            new_name = c2.text_input("名稱")
            new_cost = c3.number_input("成本", value=0.0)
            new_shares = c4.number_input("股數 (張)", value=1) * 1000
            
            if st.form_submit_button("確認新增"):
                if new_code and new_name:
                    st.session_state.portfolio.append({
                        "code": new_code, "name": new_name, "cost": new_cost, "shares": new_shares
                    })
                    st.success(f"已新增 {new_name} ({new_code})")
                    st.rerun()

    # --- 刪除功能 ---
    st.divider()
    st.subheader("📋 目前持股清單")
    if st.session_state.portfolio:
        for idx, s in enumerate(st.session_state.portfolio):
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.write(f"**{s['name']} ({s['code']})** - 成本: {s['cost']} / 股數: {s['shares']}")
            if col2.button("🗑️ 刪除", key=f"del_{s['code']}_{idx}"):
                st.session_state.portfolio.pop(idx)
                st.rerun()
    else:
        st.info("目前無庫存標的")

# ==========================================
# 3. 主導航
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室")
    page = st.sidebar.radio("導航", ["📊 庫存戰術看板", "🎯 全市場掃描", "➕ 庫存管理"])
    
    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "🎯 全市場掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__":
    main()
