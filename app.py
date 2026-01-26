import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 基礎環境設定
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0'}

st.set_page_config(page_title="鷹眼股市戰情室", page_icon="🦅", layout="wide")

# 初始化 Session State (核心數據存儲)
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 核心函數庫
# ==========================================

@st.cache_data(ttl=3600*12)
def get_stock_list():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False, timeout=5)
        res.encoding = 'big5'
        df = pd.read_html(StringIO(res.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:][df['CFICode'] == 'ESVUFR']
        return {p[0].strip(): p[1].strip() for p in (i.split('\u3000') for i in df['有價證券代號及名稱']) if len(p[0].strip()) == 4}
    except: return {"2330": "台積電", "2337": "旺宏", "4916": "事欣科", "2344": "華邦電", "2408": "南亞科"}

def calculate_indicators(df):
    close = df['Close']
    # RSI
    delta = close.diff(); g = (delta.where(delta > 0, 0)).rolling(14).mean(); l = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = (100 - (100 / (1 + g/l))).iloc[-1]
    # KD
    rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
    k = rsv.ewm(com=2).mean().iloc[-1]
    d = k.ewm(com=2).mean() # 此處簡化
    # MA20 & 乖離
    ma20 = close.rolling(20).mean().iloc[-1]
    bias = ((close.iloc[-1] - ma20) / ma20) * 100
    return rsi, k, ma20, bias

# ==========================================
# 2. 主導航與分頁實體化 (確保每個分頁都能點擊)
# ==========================================

st.sidebar.title("🦅 鷹眼戰術中心 v10.8")
page = st.sidebar.radio("分頁導航", ["📊 庫存看板", "🎯 市場掃描", "➕ 庫存管理"])

# --- 分頁 1: 庫存看板 ---
if page == "📊 庫存看板":
    st.header("📊 庫存即時戰情")
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
                    
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"損益：<span style='color:{pf_color}; font-weight:bold;'>{int(profit):+,} ({prof_pct:.2f}%)</span>", unsafe_allow_html=True)
                        st.divider()
                        st.markdown(f"🎯 **建議停利**：<span style='color:red;'>{last_p * 1.1:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"🛡️ **建議停損**：<span style='color:green;'>{s['cost'] * 0.95:.2f}</span>", unsafe_allow_html=True)
            except: st.error(f"{s['code']} 讀取失敗")

# --- 分頁 2: 市場掃描 ---
elif page == "🎯 市場掃描":
    st.header("🎯 全市場自動掃描")
    with st.sidebar:
        st.divider()
        st.write("### ⚙️ 戰術設定")
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
        min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)

    if st.button("🚀 啟動掃擊", type="primary"):
        stock_map = get_stock_list()
        res = []
        bar = st.progress(0); status = st.empty()
        for i, (c, n) in enumerate(stock_map.items()):
            status.text(f"分析中: {c} {n}...")
            bar.progress((i+1)/len(stock_map))
            try:
                df = yf.Ticker(f"{c}.TW").history(period="60d")
                if not df.empty and df['Volume'].iloc[-1] >= min_vol*1000:
                    last_p = df['Close'].iloc[-1]
                    ma20 = df['Close'].rolling(20).mean().iloc[-1]
                    if last_p >= ma20:
                        fut_ret = (df['Close'].shift(-10) - df['Close']) / df['Close'] * 100
                        win10 = (fut_ret >= target_rise).sum() / fut_ret.count() * 100
                        if win10 >= min_win10:
                            res.append({"選取": True, "代號": c, "名稱": n, "收盤價": last_p, "10日勝率%": win10})
            except: continue
        st.session_state.scan_results = pd.DataFrame(res)
        status.success(f"掃描完成！共找到 {len(res)} 檔。")

    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        if st.button("🏆 執行深度 AI 評測"):
            st.divider()
            selected = edited_df[edited_df["選取"]]
            t_cols = st.columns(len(selected) if len(selected) < 4 else 3)
            for i, (_, row) in enumerate(selected.iterrows()):
                with t_cols[i % 3]:
                    df_all = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                    rsi, k, ma20, bias = calculate_indicators(df_all)
                    with st.container(border=True):
                        st.write(f"### {row['名稱']} ({row['代號']})")
                        st.write(f"**RSI 強度**")
                        st.progress(int(rsi)/100, text=f"{rsi:.1f}")
                        st.write(f"KD 狀態: {'🔥 金叉續攻' if k > 50 else '🧊 整理中'}")
                        st.write(f"乖離狀況: {'🔴 危險' if bias > 10 else '🟢 安全'}")
                        st.divider()
                        st.markdown(f"🎯 **建議停利**: <span style='color:red;'>{row['收盤價']*1.1:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"🛡️ **建議停損**: <span style='color:green;'>{ma20:.2f}</span>", unsafe_allow_html=True)

# --- 分頁 3: 庫存管理 ---
elif page == "➕ 庫存管理":
    st.header("➕ 持股庫存管理")
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        code, name = c1.text_input("代號"), c2.text_input("名稱")
        cost, shares = c3.number_input("成本", value=0.0), c4.number_input("張數", value=1)
        if st.form_submit_button("確認存入"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
            st.rerun()
    
    st.subheader("📋 庫存清單")
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']} | {s['shares']/1000} 張")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx)
            st.rerun()
