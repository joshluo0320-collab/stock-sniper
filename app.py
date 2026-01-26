import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from io import StringIO

# ==========================================
# 0. 系統配置與模式定義
# ==========================================
st.set_page_config(page_title="鷹眼雙模戰術中心", page_icon="🦅", layout="wide")

# 初始化 Session (傳給別人不共通，但在您的瀏覽器會保留)
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 1. 鐵血教條與白話解釋邏輯
# ==========================================
def get_rank_desc(val, mode):
    if mode == "右側順勢 (10D)":
        if val < 40: return f"{val:.2f}% (📈 穩健區：右側起步)"
        if val < 80: return f"{val:.2f}% (🚀 衝刺區：動能狙擊)"
        return f"{val:.2f}% (💀 超標區：登頂危險)"
    else:
        if val < 15: return f"{val:.2f}% (💎 底部區：左側黃金埋伏)"
        return f"{val:.2f}% (尋底中：尚未跌透)"

with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v14.0")
    trade_mode = st.radio("⚔️ 選擇交易模式", ["右側順勢 (10D)", "左側逆勢 (22D)"])
    st.divider()
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場掃描", "➕ 庫存管理"])
    st.divider()
    st.error("🦾 **鐵血紀律中心**")
    st.warning("⚠️ 該走就走，頭也不回！")
    st.success("🎯 守 SOP 是唯一勝算！")

# ==========================================
# 2. 功能頁面實體化
# ==========================================

# --- [A] 庫存戰情 (修正事欣科損益與精度) ---
if page == "📊 庫存戰情":
    st.header(f"📊 {trade_mode} - 即時監控")
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
                        st.markdown(f"總損益：**{total_pnl:+,}**")
                        st.write(f"🛡️ **鐵血停損**: {round(s['cost']*0.95, 2)}")
            except: st.error(f"{s['code']} 讀取失敗")

# --- [B] 市場掃描 (修正掃描按鈕觸發機制) ---
elif page == "🎯 市場掃描":
    st.header(f"🎯 {trade_mode} - 1064 樣本自動分析")
    
    with st.sidebar:
        st.divider()
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
        min_win = st.slider("🔥 最低勝率 (%)", 0, 100, 40)

    # 確保按鈕在點擊後能確實執行完整迴圈
    run_scan = st.button("🚀 啟動全市場掃擊", type="primary")
    
    if run_scan:
        res_list = []
        try:
            url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            df_list = pd.read_html(requests.get(url, verify=False, timeout=10).text)[0]
            df_list.columns = df_list.iloc[0]
            # 確保 1064 支全樣本
            stock_map = {p[0].strip(): p[1].strip() for p in (i.split('\u3000') for i in df_list.iloc[1:][df_list['CFICode'] == 'ESVUFR']['有價證券代號及名稱']) if len(p[0].strip()) == 4}
            
            bar = st.progress(0); status = st.empty(); total = len(stock_map)
            days = 10 if trade_mode == "右側順勢 (10D)" else 22
            
            for i, (c, n) in enumerate(stock_map.items()):
                status.text(f"分析中 ({i+1}/{total}): {n} ({c})...")
                bar.progress((i+1)/total)
                try:
                    df = yf.Ticker(f"{c}.TW").history(period="1y")
                    if not df.empty and df['Volume'].iloc[-1] >= min_vol*1000:
                        ret = (df['Close'].shift(-days) - df['Close']) / df['Close'] * 100
                        w_rate = (ret >= target_rise).sum() / ret.count() * 100
                        if w_rate >= min_win:
                            res_list.append({"選取": True, "代號": c, "名稱": n, "勝率%": round(w_rate, 2), "收盤價": round(df['Close'].iloc[-1], 2)})
                except: continue
            
            st.session_state.scan_results = pd.DataFrame(res_list)
            status.success(f"掃描完成！找到 {len(res_list)} 檔標的。")
        except Exception as e:
            st.error(f"掃描中斷：{e}")

    if st.session_state.scan_results is not None:
        edited_df = st.data_editor(st.session_state.scan_results, hide_index=True, use_container_width=True)
        if st.button("🏆 執行深度 AI 評測 (預測走揚時點)"):
            deep_list = []
            selected = edited_df[edited_df["選取"] == True]
            for _, row in selected.iterrows():
                try:
                    df_all = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                    close = df_all['Close']
                    l60, h60 = close.tail(60).min(), close.tail(60).max()
                    rank = ((close.iloc[-1] - l60) / (h60 - l60)) * 100
                    
                    pred = "遵循趨勢訊號"
                    if trade_mode == "左側逆勢 (22D)":
                        vol_ratio = df_all['Volume'].iloc[-1] / df_all['Volume'].tail(5).mean()
                        pred = "⚡ 預計 3-5 天內反彈" if vol_ratio < 0.7 else "⏳ 築底中 (1-2週)"

                    deep_list.append({
                        "名稱": row['名稱'], "代號": row['代號'], "現價": row['收盤價'],
                        "勝率%": row['勝率%'], "位階(貴不貴)": get_rank_desc(rank, trade_mode),
                        "走揚預測": pred, "🛡️ 鐵血停損": round(row['收盤價']*0.95, 2)
                    })
                except: continue
            st.table(pd.DataFrame(deep_list).sort_values(by="勝率%", ascending=False))

# --- [C] 庫存管理 (確保新增刪除與 Rerun 同步) ---
elif page == "➕ 庫存管理":
    st.header("➕ 持股庫存管理")
    with st.form("add_stock", clear_on_submit=True):
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
