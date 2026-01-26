import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from io import StringIO

# ==========================================
# 0. 基礎配置與 Session 初始化
# ==========================================
st.set_page_config(page_title="鷹眼戰術中心", page_icon="🦅", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 核心工具函數
# ==========================================
def get_rank_info(val):
    if val < 20: return f"{val:.2f}% (💎 底部：低風險)"
    if val < 50: return f"{val:.2f}% (📈 穩健：趨勢中)"
    if val < 80: return f"{val:.2f}% (🚀 衝刺：熱度高)"
    return f"{val:.2f}% (💀 超標：登頂危險)"

def get_rsi_info(val):
    if val > 70: return f"{val:.2f} (🔥 瘋狂：全民瘋搶)"
    if val > 50: return f"{val:.2f} (🚀 動能：有人追價)"
    return f"{val:.2f} (🧊 觀望：熱度一般)"

# ==========================================
# 2. 鐵血左側面板 (強制固定不變)
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v13.5")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    if page == "🎯 市場掃描":
        st.subheader("⚙️ 掃描參數")
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
        min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
        st.divider()
    
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ **該走就走，頭也不回！**")
    st.error("💀 **妖股無情，心魔必斬！**")
    st.success("🎯 **守 SOP 是唯一勝算！**")

# ==========================================
# 3. 功能頁面實體化 (確保 A, B, C 同時運作)
# ==========================================

# --- [A] 庫存戰情 ---
if page == "📊 庫存戰情":
    st.header("📊 持股即時監控 (已修正損益計算)")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                h = t.history(period="5d")
                if not h.empty:
                    last_p = round(float(h.iloc[-1]['Close']), 2)
                    total_pnl = round((last_p - s['cost']) * s['shares'], 2)
                    p_color = "red" if last_p >= h.iloc[-2]['Close'] else "green"
                    with st.container(border=True):
                        st.subheader(f"{s['name']} ({s['code']})")
                        st.markdown(f"現價：<span style='color:{p_color}; font-size:26px; font-weight:bold;'>{last_p}</span>", unsafe_allow_html=True)
                        st.markdown(f"總損益：<span style='color:{'red' if total_pnl >= 0 else 'green'}; font-weight:bold;'>{total_pnl:+,}</span>", unsafe_allow_html=True)
                        st.divider()
                        st.write(f"🛡️ **鐵血停損**: {round(s['cost']*0.95, 2)} | 🎯 **建議停利**: {round(s['cost']*1.1, 2)}")
            except: st.error(f"{s['code']} 讀取失敗")

# --- [B] 市場掃描 ---
elif page == "🎯 市場掃描":
    st.header("🎯 全市場 1064 樣本自動掃描")
    if st.button("🚀 啟動全市場掃擊", type="primary"):
        res_list = []
        try:
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
                            ret5 = (df['Close'].shift(-5) - df['Close']) / df['Close'] * 100
                            res_list.append({"選取": True, "代號": c, "名稱": n, "10日勝率%": round(w10, 2), "5日勝率%": round((ret5 >= target_rise).sum() / ret5.count() * 100, 2), "收盤價": round(df['Close'].iloc[-1], 2)})
                except: continue
            st.session_state.scan_results = pd.DataFrame(res_list)
            status.success(f"完成！找到 {len(res_list)} 檔。")
        except: st.error("證交所連線超時。")

    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True)
        if st.button("🏆 執行深度 AI 表格評測"):
            st.divider(); deep_list = []
            selected = edited_df[edited_df["選取"] == True]
            for _, row in selected.iterrows():
                try:
                    df_all = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                    close = df_all['Close']
                    l60, h60 = close.tail(60).min(), close.tail(60).max()
                    rank = ((close.iloc[-1] - l60) / (h60 - l60)) * 100 if h60 != l60 else 50
                    delta = close.diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = -delta.where(delta < 0, 0).rolling(14).mean(); rsi = (100 - (100 / (1 + g/l))).iloc[-1]
                    ema12 = close.ewm(span=12).mean(); ema26 = close.ewm(span=26).mean(); dif = ema12 - ema26; macd = dif.ewm(span=9).mean(); osc = (dif - macd).iloc[-1]
                    deep_list.append({"名稱": row['名稱'], "代號": row['代號'], "現價": row['收盤價'], "10日勝率%": f"{row['10日勝率%']}%", "位階%": get_rank_info(rank), "力道(RSI)": get_rsi_info(rsi), "MACD": "⛽ 滿油" if osc > 0 else "🛑 減速", "🛡️ 鐵血停損": round(row['收盤價']*0.95, 2), "🎯 停利": round(row['收盤價']*1.1, 2)})
                except: continue
            st.table(pd.DataFrame(deep_list).sort_values(by="10日勝率%", ascending=False))

# --- [C] 庫存管理 ---
elif page == "➕ 庫存管理":
    st.header("➕ 庫存清單優化")
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        code, name = c1.text_input("代號"), c2.text_input("名稱")
        cost, shares = c3.number_input("成本", value=0.0), c4.number_input("張數", value=1)
        if st.form_submit_button("確認存入"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
            st.rerun()
    st.divider()
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2 = st.columns([5, 1])
        col1.write(f"**{s['name']} ({s['code']})** | 成本: {s['cost']} | {int(s['shares']/1000)} 張")
        if col2.button("🗑️ 刪除", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx); st.rerun()
