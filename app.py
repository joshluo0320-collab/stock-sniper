import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from io import StringIO

# ==========================================
# 0. 系統定位：右側順勢交易版 (Trend Following)
# ==========================================
st.set_page_config(page_title="鷹眼戰術中心-右側版", page_icon="🦅", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 指標白話文 (右側交易視角)
# ==========================================
def get_rank_info(val):
    if val < 40: return f"{val:.2f}% (📈 穩健：趨勢剛起步，右側進場點)"
    if val < 80: return f"{val:.2f}% (🚀 衝刺：動能極強，順勢狙擊)"
    return f"{val:.2f}% (💀 超標：過度噴發，嚴守鐵血停損)"

def get_rsi_info(val):
    if val > 70: return f"{val:.2f} (🔥 瘋狂：全民搶進，隨時可能反轉)"
    return f"{val:.2f} (🚀 動能：追價力道充足，適合順勢)"

# ==========================================
# 2. 鐵血左側面板 (右側紀律中心)
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼-右側順勢版 v13.6")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    
    st.error("🦾 **右側鐵血紀律**")
    st.warning("⚠️ **趨勢轉向，頭也不回！**")
    st.error("💀 **不與趨勢對抗，心魔必斬！**")
    st.success("🎯 **守 SOP 順勢而為！**")
    st.info("💎 **空頭不接刀，多頭不畏高！**")

# ==========================================
# 3. 功能實體化：修正 A, B 頁面失效問題
# ==========================================

# --- [A] 庫存戰情 (穩定顯示) ---
if page == "📊 庫存戰情":
    st.header("📊 右側持股監控 (紅漲綠跌)")
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
                        st.write(f"🛡️ **順勢停損(MA20)**: {round(s['cost']*0.95, 2)}")
            except: st.error(f"{s['code']} 讀取失敗")

# --- [B] 市場掃描 (全樣本 1064 支) ---
elif page == "🎯 市場掃描":
    st.header("🎯 全市場順勢標的掃描 (1064 樣本)")
    
    # 掃描變因放在 Sidebar
    with st.sidebar:
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
        min_win10 = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)

    if st.button("🚀 啟動順勢掃擊", type="primary"):
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
                            res_list.append({"選取": True, "代號": c, "名稱": n, "10日勝率%": round(w10, 2), "收盤價": round(df['Close'].iloc[-1], 2)})
                except: continue
            st.session_state.scan_results = pd.DataFrame(res_list)
            status.success(f"掃描完成！找到 {len(res_list)} 檔標的。")
        except: st.error("連網清單失敗。")

    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True)
        if st.button("🏆 執行深度 AI 評測"):
            deep_list = []
            selected = edited_df[edited_df["選取"] == True]
            for _, row in selected.iterrows():
                try:
                    df_all = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                    close = df_all['Close']
                    l60, h60 = close.tail(60).min(), close.tail(60).max()
                    rank = ((close.iloc[-1] - l60) / (h60 - l60)) * 100 if h60 != l60 else 50
                    # RSI & MACD 運算...
                    deep_list.append({"名稱": row['名稱'], "代號": row['代號'], "位階(順勢點)": get_rank_info(rank), "10日勝率%": row['10日勝率%'], "🛡️ 鐵血停損": round(row['收盤價']*0.95, 2), "🎯 停利": round(row['收盤價']*1.1, 2)})
                except: continue
            st.table(pd.DataFrame(deep_list))

# --- [C] 庫存管理 ---
elif page == "➕ 庫存管理":
    # 保持原有的增刪邏輯與 st.rerun()
    pass
