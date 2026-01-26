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

# 初始化記憶
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 自動抓取清單函數
# ==========================================
@st.cache_data(ttl=3600*12)
def get_stock_list():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        response = requests.get(url, verify=False, timeout=5)
        response.encoding = 'big5'
        df = pd.read_html(StringIO(response.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:][df['CFICode'] == 'ESVUFR']
        return {p[0].strip(): p[1].strip() for p in (item.split('\u3000') for item in df['有價證券代號及名稱']) if len(p[0].strip()) == 4}
    except: return {"2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2337": "旺宏", "4916": "事欣科"}

# ==========================================
# 2. 各頁面模組實作
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
                    p_color = "red" if chg >= 0 else "green"
                    pf_color = "red" if profit >= 0 else "green"
                    
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:24px; font-weight:bold;'>{last_p:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"損益：<span style='color:{pf_color}; font-weight:bold;'>{int(profit):+,} ({prof_pct:.2f}%)</span>", unsafe_allow_html=True)
                        st.divider()
                        if s['code'] == "4916": st.info("💡 建議：67.0 獲利保衛")
                        elif s['code'] == "2337": st.success("🚀 強勢：續抱參與噴發")
            except: st.error(f"{s['code']} 更新失敗")

def page_scanner():
    st.header("🎯 市場自動掃描")
    stock_map = get_stock_list()
    
    with st.sidebar:
        st.header("⚙️ 戰術控制台")
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
        min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
        st.success("✅ 已強制開啟：股價 > 月線")

    if st.button("🚀 啟動全市場掃描", type="primary"):
        res = []
        bar = st.progress(0)
        status = st.empty()
        for i, (code, name) in enumerate(stock_map.items()):
            status.text(f"分析中：{code} {name}...")
            bar.progress((i+1)/len(stock_map))
            # 簡化掃描邏輯，僅抓取符合基本門檻的資料
            try:
                df = yf.Ticker(f"{code}.TW").history(period="1y")
                if not df.empty and df['Volume'].iloc[-1] >= min_vol*1000:
                    last_p = df['Close'].iloc[-1]
                    ma20 = df['Close'].rolling(20).mean().iloc[-1]
                    if last_p >= ma20:
                        fut_ret = (df['Close'].shift(-10) - df['Close']) / df['Close'] * 100
                        win10 = (fut_ret >= target_rise).sum() / fut_ret.count() * 100
                        if win10 >= min_win10:
                            res.append({"選取": True, "代號": code, "名稱": name, "收盤價": last_p, "10日勝率%": win10})
            except: continue
        st.session_state.scan_results = pd.DataFrame(res)
        status.success(f"掃描完成！找到 {len(res)} 檔。")

    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        if st.button("🏆 執行深度 AI 評測"):
            st.divider()
            for _, row in edited_df[edited_df["選取"]].iterrows():
                with st.container(border=True):
                    st.write(f"### {row['名稱']} ({row['代號']})")
                    st.write(f"10日勝率: {row['10日勝率%']:.1f}% | 建議進場: {row['收盤價']}")

def page_management():
    st.header("➕ 庫存管理")
    with st.form("add_stock"):
        c1, c2, c3, c4 = st.columns(4)
        code, name = c1.text_input("代號"), c2.text_input("名稱")
        cost, shares = c3.number_input("成本", value=0.0), c4.number_input("張數", value=1)
        if st.form_submit_button("確認新增"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
            st.rerun()
    
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']} | {s['shares']/1000} 張")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx)
            st.rerun()

# ==========================================
# 3. 主導航
# ==========================================
def main():
    st.sidebar.title("🦅 戰術中心")
    page = st.sidebar.radio("分頁", ["📊 庫存看板", "🎯 市場掃描", "➕ 庫存管理"])
    if page == "📊 庫存看板": page_dashboard()
    elif page == "🎯 市場掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__": main()
