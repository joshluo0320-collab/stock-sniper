import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 系統環境與 SSL 設定
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

st.set_page_config(page_title="鷹眼戰術中心", page_icon="🦅", layout="wide")

# 初始化記憶：庫存與掃描結果
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 核心函數庫 (樣本抓取與指標)
# ==========================================

@st.cache_data(ttl=3600*12)
def get_stock_list_full():
    """鎖定全市場 1000+ 上市普通股清單"""
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False, timeout=10)
        res.encoding = 'big5'
        df = pd.read_html(StringIO(res.text))[0]
        df.columns = df.iloc[0]
        # 關鍵濾網：ESVUFR 代表上市普通股，確保樣本數精確
        df = df.iloc[1:][df['CFICode'] == 'ESVUFR']
        return {p[0].strip(): p[1].strip() for p in (i.split('\u3000') for i in df['有價證券代號及名稱']) if len(p[0].strip()) == 4}
    except:
        return {"2330": "台積電", "1623": "大東電"} # 備援僅限斷網

def analyze_indicators(df):
    """計算 MACD, RSI, KD 與位階"""
    close = df['Close']
    # 位階：(現價 - 60日最低) / (60日最高 - 60日最低)
    l60, h60 = close.tail(60).min(), close.tail(60).max()
    rank = ((close.iloc[-1] - l60) / (h60 - l60)) * 100 if h60 != l60 else 50
    # RSI
    delta = close.diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = -delta.where(delta < 0, 0).rolling(14).mean()
    rsi = (100 - (100 / (1 + g/l))).iloc[-1]
    # MACD
    ema12 = close.ewm(span=12).mean(); ema26 = close.ewm(span=26).mean(); dif = ema12 - ema26; macd = dif.ewm(span=9).mean(); osc = dif - macd
    return rank, rsi, osc.iloc[-1]

# ==========================================
# 2. 鐵血左側面板 (Sidebar)
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v12.0")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    st.header("⚙️ 掃描變因")
    min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
    target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
    min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
    st.divider()
    
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ **該走就走，頭也不回！**")
    st.error("💀 **妖股無情，心魔必斬！**")
    st.success("🎯 **守 SOP 是唯一勝算！**")
    st.info("💎 **本金是命，沒了就出局！**")

# ==========================================
# 3. 分頁功能實體化
# ==========================================

if page == "📊 庫存戰情":
    st.header("📊 庫存即時監控 (紅漲綠跌)")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                h = t.history(period="10d")
                if not h.empty:
                    last_p, prev_p = h.iloc[-1]['Close'], h.iloc[-2]['Close']
                    p_color = "red" if last_p >= prev_p else "green"
                    pf_color = "red" if (last_p - s['cost']) >= 0 else "green"
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p:.2f}</span>", unsafe_allow_html=True)
                        st.markdown(f"損益：<span style='color:{pf_color}; font-weight:bold;'>{(last_p - s['cost']) * s['shares']:+,}</span>", unsafe_allow_html=True)
                        st.divider()
                        st.write(f"🎯 **目標停利**: {s['cost']*1.1:.2f}")
                        st.write(f"🛡️ **鐵血停損**: {s['cost']*0.95:.2f}")
            except: st.error(f"{s['code']} 逾時")

elif page == "🎯 市場掃描":
    st.header("🎯 全市場 1000+ 樣本自動掃描")
    if st.button("🚀 啟動全市場掃擊", type="primary"):
        stock_map = get_stock_list_full()
        res = []
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
                        ret5 = (df['Close'].shift(-5) - df['Close']) / df['Close'] * 100
                        w5 = (ret5 >= target_rise).sum() / ret5.count() * 100
                        res.append({"選取": True, "代號": c, "名稱": n, "10日勝率%": w10, "5日勝率%": w5})
            except: continue
        st.session_state.scan_results = pd.DataFrame(res)
        status.success(f"完成！找到 {len(res)} 檔。")

    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        if st.button("🏆 執行深度 AI 表格評測"):
            st.divider(); deep_list = []
            for _, row in edited_df[edited_df["選取"]].iterrows():
                df_all = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                rank, rsi, osc = analyze_indicators(df_all)
                last_p = df_all['Close'].iloc[-1]
                deep_list.append({
                    "名稱": row['名稱'], "代號": row['代號'], "現價": last_p,
                    "10日勝率%": row['10日勝率%'], "5日勝率%": row['5日勝率%'],
                    "位階%": f"{rank:.1f}% ({'💎' if rank<20 else '🚀' if rank>80 else '📈'})",
                    "MACD": "⛽ 滿油" if osc > 0 else "🛑 減速",
                    "RSI": "🔥 強" if rsi > 50 else "🧊 弱",
                    "建議進場": last_p, "🛡️ 鐵血停損": last_p * 0.95, "🎯 目標停利": last_p * 1.1
                })
            final_df = pd.DataFrame(deep_list).sort_values(by="10日勝率%", ascending=False)
            st.subheader("🥇 深度決策表格 (按參考價值排序)")
            st.table(final_df)

elif page == "➕ 庫存管理":
    st.header("➕ 庫存清單管理")
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        code, name = c1.text_input("代號"), c2.text_input("名稱")
        cost, shares = c3.number_input("成本", value=0.0), c4.number_input("張數", value=1)
        if st.form_submit_button("確認存入"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
            st.rerun()
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']} | {s['shares']/1000} 張")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx); st.rerun()
