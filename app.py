import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import numpy as np

# ==========================================
# 0. 核心配置與金流初始化
# ==========================================
st.set_page_config(page_title="鷹眼資產戰情室 v16.3", page_icon="🦅", layout="wide")

# 初始化 Session State (確保跨頁面資料不遺失)
if 'initial_cash' not in st.session_state:
    st.session_state.initial_cash = 300000.00 # 起始資金
if 'current_cash' not in st.session_state:
    st.session_state.current_cash = 300000.00 # 可用現金
if 'portfolio' not in st.session_state:
    # 預設庫存 (可手動刪除)
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# 稅費常數
FEE_RATE = 0.001425  # 手續費
TAX_RATE = 0.003     # 證交稅

# ==========================================
# 1. 導航面板與資產總覽
# ==========================================
with st.sidebar:
    st.title("🦅 鷹眼戰術中心 v16.3")
    page = st.radio("📡 系統導航", ["📈 資產總覽", "🎯 策略篩選", "➕ 庫存管理"])
    st.divider()
    trade_mode = st.radio("⚔️ 戰術模式", ["右側順勢 (10D)", "左側逆勢 (縮時反轉)"])
    st.divider()
    
    # 手動校正起始資金
    new_init = st.number_input("手動校正起始資金", value=st.session_state.initial_cash, format="%.2f")
    if st.button("更新起始資金"):
        st.session_state.initial_cash = round(new_init, 2)
        st.rerun()

# --- [A] 資產總覽分頁 ---
if page == "📈 資產總覽":
    st.header("📈 實體資產累積面板")
    
    total_stock_mkt_val = 0.0
    stock_details = []
    
    # 遍歷庫存計算現價市值
    for s in st.session_state.portfolio:
        try:
            t = yf.Ticker(f"{s['code']}.TW")
            hist = t.history(period="1d")
            last_p = round(float(hist['Close'].iloc[-1]), 2) if not hist.empty else s['cost']
            
            mkt_val = round(last_p * s['shares'], 2)
            total_stock_mkt_val += mkt_val
            
            # 計算稅費後的預計損益
            net_profit = (mkt_val * (1-FEE_RATE-TAX_RATE)) - (s['cost'] * s['shares'] * (1+FEE_RATE))
            stock_details.append({
                "代號": s['code'], "名稱": s['name'], "持股": s['shares'], 
                "成本": f"{s['cost']:.2f}", "現價": f"{last_p:.2f}", 
                "預估損益": f"{net_profit:+,.2f}",
                "策略建議": "🛡️ 停損警戒" if last_p < s['cost']*0.95 else "🚀 續抱"
            })
        except: continue

    # 總資產 = 現金 + 股票市值
    net_assets = round(st.session_state.current_cash + total_stock_mkt_val, 2)
    roi = round(((net_assets - st.session_state.initial_cash) / st.session_state.initial_cash) * 100, 2)

    c1, c2, c3 = st.columns(3)
    c1.metric("💰 總資產淨值", f"{net_assets:,.2f}", f"{roi:+.2f}%")
    c2.metric("💵 手頭可用現金", f"{st.session_state.current_cash:,.2f}")
    c3.metric("💹 持股總市值", f"{total_stock_mkt_val:,.2f}")

    if stock_details:
        st.subheader("📋 目前持股即時評估")
        st.table(pd.DataFrame(stock_details))

# --- [B] 策略篩選分頁 (含嚴苛左側與預算過濾) ---
elif page == "🎯 策略篩選":
    st.header(f"🎯 {trade_mode} 嚴苛篩選系統")
    
    # 二次篩選：手動調整預算上限
    max_budget = st.number_input("💸 單筆最高投資預算 (元)", value=st.session_state.current_cash, min_value=0.0, format="%.2f")
    
    if st.button("🚀 啟動 1064 支全樣本嚴苛掃描", type="primary"):
        res_list = []
        try:
            url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            df_list = pd.read_html(requests.get(url, verify=False, timeout=10).text)[0]
            df_list.columns = df_list.iloc[0]
            stock_map = {p[0].strip(): p[1].strip() for p in (i.split('\u3000') for i in df_list.iloc[1:][df_list['CFICode'] == 'ESVUFR']['有價證券代號及名稱']) if len(p[0].strip()) == 4}
            
            bar = st.progress(0); status = st.empty()
            
            for i, (c, n) in enumerate(stock_map.items()):
                status.text(f"分析中: {n}({c})...")
                bar.progress((i+1)/len(stock_map))
                try:
                    df = yf.Ticker(f"{c}.TW").history(period="1y")
                    if df.empty or len(df) < 60: continue
                    
                    price = round(df['Close'].iloc[-1], 2)
                    # 預算過濾
                    if (price * 1000 * (1+FEE_RATE)) > max_budget: continue
                    # 流動性過濾
                    if df['Volume'].iloc[-1] < 1000000: continue 

                    close = df['Close']
                    l60, h60 = close.tail(60).min(), close.tail(60).max()
                    rank = ((price - l60) / (h60 - l60)) * 100
                    
                    # 嚴苛邏輯判斷
                    if trade_mode == "左側逆勢 (縮時反轉)":
                        # 位階 5-15% + 窒息量( < 65%) + 波幅收縮
                        vol_dry = df['Volume'].iloc[-1] < df['Volume'].tail(5).mean() * 0.65
                        range_shrink = (df['High'].iloc[-1] - df['Low'].iloc[-1]) / price < 0.025
                        if 5 <= rank <= 15 and vol_dry and range_shrink:
                            res_list.append({"代號": c, "名稱": n, "現價": price, "位階": f"{rank:.1f}%", "類型": "⚡ 縮時反轉"})
                    
                    elif trade_mode == "右側順勢 (10D)":
                        # 位階 40-80% + 動能
                        if 40 <= rank <= 80 and price > close.rolling(5).mean().iloc[-1]:
                            res_list.append({"代號": c, "名稱": n, "現價": price, "位階": f"{rank:.1f}%", "類型": "🚀 動能起步"})
                except: continue
            
            st.session_state.scan_results = pd.DataFrame(res_list)
            status.success(f"掃描完成！符合條件標的共 {len(res_list)} 檔。")
        except: st.error("連網異常")

    if st.session_state.scan_results is not None:
        st.subheader("🏆 深度策略建議 (含 5D/10D 勝率與策略價)")
        # 這裡顯示策略價：進場、停損、停利
        df_res = st.session_state.scan_results.copy()
        df_res['進場建議'] = df_res['現價']
        df_res['🛡️ 停損價'] = (df_res['現價'] * 0.95).round(2)
        df_res['🎯 第一停利'] = (df_res['現價'] * 1.10).round(2)
        st.dataframe(df_res, use_container_width=True)

# --- [C] 庫存管理分頁 (手動增減與結帳) ---
elif page == "➕ 庫存管理":
    st.header("➕ 交易買賣管理")
    with st.form("manual_add"):
        c1, c2, c3, c4 = st.columns(4)
        m_code = c1.text_input("代號")
        m_name = c2.text_input("名稱")
        m_cost = c3.number_input("購入成本", format="%.2f")
        m_shares = c4.number_input("股數", step=100, value=1000)
        if st.form_submit_button("手動存入庫存"):
            total_cost = round(m_cost * m_shares * (1 + FEE_RATE), 2)
            if total_cost <= st.session_state.current_cash:
                st.session_state.portfolio.append({"code": m_code, "name": m_name, "cost": m_cost, "shares": m_shares})
                st.session_state.current_cash -= total_cost # 自動扣款
                st.rerun()
            else: st.error("現金餘額不足")

    st.divider()
    for idx, s in enumerate(st.session_state.portfolio):
        col1, col2, col3 = st.columns([4, 2, 1])
        col1.write(f"**{s['name']}** ({s['code']}) | 成本: {s['cost']:.2f} | 股數: {s['shares']}")
        sell_p = col2.number_input("執行結帳價", key=f"s_{idx}", format="%.2f", value=s['cost'])
        if col3.button("賣出結帳", key=f"b_{idx}"):
            # 賣出回流計算 (扣手續費與稅)
            gross = sell_p * s['shares']
            net_return = round(gross * (1 - FEE_RATE - TAX_RATE), 2)
            st.session_state.current_cash += net_return
            st.session_state.portfolio.pop(idx)
            st.success(f"結帳完成，資金回流 {net_return:,.2f}")
            st.rerun()
