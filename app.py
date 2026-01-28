import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# ==========================================
# 0. 系統配置與 30 萬金流初始化
# ==========================================
st.set_page_config(page_title="鷹眼戰術中心-整合版", page_icon="🦅", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 300000.0  # 起始資金 30 萬
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None
if 'history' not in st.session_state:
    st.session_state.history = []

FEE_RATE = 0.001425  # 手續費
TAX_RATE = 0.003     # 證交稅

# ==========================================
# 1. 側邊欄：模式切換與資金看板
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v15.5")
    trade_mode = st.radio("⚔️ 選擇交易模式", ["右側順勢 (10D)", "左側逆勢 (22D)"])
    st.divider()
    st.metric("💰 目前可用資金", f"{st.session_state.cash:,.0f} 元")
    page = st.radio("📡 戰情導航", ["📊 庫存戰情", "🎯 市場篩選", "➕ 庫存管理", "📑 歷史對帳"])
    st.divider()
    st.error("🦾 **鐵血紀律**")
    st.warning("⚠️ 趨勢轉向，頭也不回！")

# ==========================================
# 2. 核心功能模組
# ==========================================

# --- [A] 庫存戰情 (含精確損益) ---
if page == "📊 庫存戰情":
    st.header(f"📊 {trade_mode} - 即時損益監控")
    cols = st.columns(3)
    for i, s in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{s['code']}.TW")
                last_p = round(float(t.history(period="1d")['Close'].iloc[-1]), 2)
                # 扣除稅費後的預估結算損益
                net_sell = (last_p * s['shares']) * (1 - FEE_RATE - TAX_RATE)
                pnl = net_sell - (s['cost'] * s['shares'] * (1 + FEE_RATE))
                with st.container(border=True):
                    st.subheader(f"{s['name']} ({s['code']})")
                    st.write(f"現價: {last_p} | 成本: {s['cost']}")
                    color = "red" if pnl >= 0 else "green"
                    st.markdown(f"預估損益: <span style='color:{color}; font-weight:bold;'>{pnl:+,.0f}</span>", unsafe_allow_html=True)
            except: st.error(f"{s['code']} 讀取中...")

# --- [B] 市場篩選 (1064 支樣本 + 資金評比) ---
elif page == "🎯 市場篩選":
    st.header(f"🎯 {trade_mode} - 全樣本篩選系統")
    with st.sidebar:
        st.subheader("⚙️ 篩選參數")
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 30, 10)
        min_win = st.slider("🔥 最低勝率 (%)", 0, 100, 40)

    if st.button("🚀 啟動 1064 支全樣本掃擊", type="primary"):
        res_list = []
        try:
            url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            df_list = pd.read_html(requests.get(url, verify=False, timeout=10).text)[0]
            df_list.columns = df_list.iloc[0]
            stock_map = {p[0].strip(): p[1].strip() for p in (i.split('\u3000') for i in df_list.iloc[1:][df_list['CFICode'] == 'ESVUFR']['有價證券代號及名稱']) if len(p[0].strip()) == 4}
            
            bar = st.progress(0); status = st.empty()
            days = 10 if trade_mode == "右側順勢 (10D)" else 22
            
            for i, (c, n) in enumerate(stock_map.items()):
                status.text(f"分析中: {n}({c})...")
                bar.progress((i+1)/len(stock_map))
                try:
                    df = yf.Ticker(f"{c}.TW").history(period="1y")
                    if not df.empty and df['Volume'].iloc[-1] >= min_vol*1000:
                        ret = (df['Close'].shift(-days) - df['Close']) / df['Close'] * 100
                        w_rate = (ret >= target_rise).sum() / ret.count() * 100
                        if w_rate >= min_win:
                            res_list.append({"選取": True, "代號": c, "名稱": n, "勝率%": round(w_rate, 2), "收盤價": round(df['Close'].iloc[-1], 2)})
                except: continue
            st.session_state.scan_results = pd.DataFrame(res_list)
            status.success(f"篩選完成！共找到 {len(res_list)} 檔標的。")
        except: st.error("連網失敗")

    if st.session_state.scan_results is not None:
        df = st.session_state.scan_results.copy()
        # 加入資金評比
        df['資金評比'] = df.apply(lambda x: "✅ 可買" if (x['收盤價']*1000*(1+FEE_RATE)) <= st.session_state.cash else "⚠️ 錢不夠", axis=1)
        edited_df = st.data_editor(df, hide_index=True, use_container_width=True)
        
        if st.button("🏆 深度分析 (含左側走揚預測)"):
            deep_list = []
            for _, row in edited_df[edited_df["選取"] == True].iterrows():
                df_all = yf.Ticker(f"{row['代號']}.TW").history(period="1y")
                close = df_all['Close']
                l60, h60 = close.tail(60).min(), close.tail(60).max()
                rank = ((close.iloc[-1] - l60) / (h60 - l60)) * 100
                pred = "遵循趨勢"
                if trade_mode == "左側逆勢 (22D)":
                    vol_ratio = df_all['Volume'].iloc[-1] / df_all['Volume'].tail(5).mean()
                    pred = "⚡ 3-5天內反彈" if vol_ratio < 0.7 else "⏳ 築底中"
                deep_list.append({"名稱": row['名稱'], "代號": row['代號'], "位階": f"{rank:.1f}%", "預測": pred, "資金": row['資金評比']})
            st.table(pd.DataFrame(deep_list))

# --- [C] 庫存管理 (含精確賣出與對帳) ---
elif page == "➕ 庫存管理":
    st.header("➕ 庫存增減與賣出結帳")
    with st.form("add"):
        c1, c2, c3, c4 = st.columns(4)
        code = c1.text_input("代號"); name = c2.text_input("名稱")
        cost = c3.number_input("成本"); shares = c4.number_input("張數", step=1)
        if st.form_submit_button("確認購入"):
            total_cost = cost * shares * 1000 * (1 + FEE_RATE)
            if total_cost <= st.session_state.cash:
                st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares*1000})
                st.session_state.cash -= total_cost
                st.rerun()
            else: st.error("資金不足")
    st.divider()
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2, col3 = st.columns([4, 2, 1])
        col1.write(f"**{s['name']}** ({s['code']}) | 成本: {s['cost']} | 持有: {int(s['shares']/1000)}張")
        sp = col2.number_input("賣出價", key=f"s_{idx}", value=s['cost'])
        if col3.button("執行賣出", key=f"b_{idx}"):
            gross = sp * s['shares']
            net_return = gross * (1 - FEE_RATE - TAX_RATE)
            st.session_state.cash += net_return
            profit = net_return - (s['cost'] * s['shares'] * (1 + FEE_RATE))
            st.session_state.history.append({"標的": s['name'], "獲利": round(profit, 0)})
            st.session_state.portfolio.pop(idx)
            st.rerun()
