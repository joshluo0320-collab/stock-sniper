import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# ==========================================
# 0. 核心配置與全局狀態 (穩定鎖定)
# ==========================================
st.set_page_config(page_title="鷹眼資產戰情室 v18.0", page_icon="🦅", layout="wide")

# 初始化所有狀態，確保切換分頁不遺失
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]
if 'initial_cash' not in st.session_state:
    st.session_state.initial_cash = 300000.00 # 起始資金
if 'current_cash' not in st.session_state:
    st.session_state.current_cash = 300000.00 # 現有現金
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

FEE_RATE = 0.001425 #
TAX_RATE = 0.003

# ==========================================
# 1. 導航面板
# ==========================================
with st.sidebar:
    st.title("🦅 戰情中心 v18.0")
    page = st.radio("📡 系統導航", ["📈 資產總覽", "🎯 策略篩選", "➕ 庫存管理"])
    st.divider()
    trade_mode = st.radio("⚔️ 戰術模式", ["右側順勢 (10D)", "左側逆勢 (縮時反轉)"])
    st.divider()
    
    # [功能 1] 手動輸入/更新資產部分 (回歸)
    st.subheader("💰 資產手動校正")
    new_init = st.number_input("起始總資金", value=float(st.session_state.initial_cash), format="%.2f")
    new_cash = st.number_input("手頭可用現金", value=float(st.session_state.current_cash), format="%.2f")
    if st.button("確認同步校正"):
        st.session_state.initial_cash = round(new_init, 2)
        st.session_state.current_cash = round(new_cash, 2)
        st.rerun()

# ==========================================
# 2. 分頁功能：資產總覽 (股票現價 + 現金)
# ==========================================
if page == "📈 資產總覽":
    st.header("📈 實體資產累積面板")
    
    total_mkt_val = 0.0
    stock_list = []
    
    for s in st.session_state.portfolio:
        try:
            t = yf.Ticker(f"{s['code']}.TW")
            h = t.history(period="1d")
            p = round(float(h['Close'].iloc[-1]), 2) if not h.empty else s['cost']
            mv = round(p * s['shares'], 2)
            total_mkt_val += mv
            # 計算損益
            pnl = (mv * (1-FEE_RATE-TAX_RATE)) - (s['cost'] * s['shares'] * (1+FEE_RATE))
            stock_list.append({"名稱": s['name'], "代號": s['code'], "成本": f"{s['cost']:.2f}", "現價": f"{p:.2f}", "預估損益": f"{pnl:+,.0f}"})
        except: continue

    net_assets = round(st.session_state.current_cash + total_mkt_val, 2)
    roi = round(((net_assets - st.session_state.initial_cash) / st.session_state.initial_cash) * 100, 2)

    c1, c2, c3 = st.columns(3)
    c1.metric("💰 總資產淨值", f"{net_assets:,.2f}", f"{roi:+.2f}%")
    c2.metric("💵 可用現金部位", f"{st.session_state.current_cash:,.2f}")
    c3.metric("💹 股票市值加總", f"{total_mkt_val:,.2f}")
    
    if stock_list: st.table(pd.DataFrame(stock_list))

# ==========================================
# 3. 分頁功能：策略篩選 (最初勝率版本回歸)
# ==========================================
elif page == "🎯 策略篩選":
    st.header(f"🎯 {trade_mode} 鷹眼篩選系統")
    
    # 預算過濾條件
    max_budget = st.number_input("💸 單筆預算上限", value=float(st.session_state.current_cash), format="%.2f")

    if st.button("🚀 啟動 1064 支全樣本掃描", type="primary"):
        res = []
        try:
            # 抓取上市清單 (最初版本邏輯)
            url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            df_list = pd.read_html(requests.get(url, verify=False, timeout=15).text)[0]
            df_list.columns = df_list.iloc[0]
            stocks = df_list.iloc[1:][df_list['CFICode'] == 'ESVUFR']['有價證券代號及名稱'].tolist()
            
            bar = st.progress(0); status = st.empty()
            days = 10 if trade_mode == "右側順勢 (10D)" else 22 # 最初設定週期

            for i, item in enumerate(stocks):
                code = item.split('\u3000')[0].strip()
                name = item.split('\u3000')[1].strip()
                if len(code) != 4: continue
                
                status.text(f"分析中: {name}({code})")
                bar.progress((i+1)/len(stocks))
                
                try:
                    df = yf.Ticker(f"{code}.TW").history(period="1y")
                    if df.empty or len(df) < 60: continue
                    
                    price = round(df['Close'].iloc[-1], 2)
                    if (price * 1000 * (1+FEE_RATE)) > max_budget: continue # 資金過濾

                    # 最初勝率計算邏輯
                    returns = (df['Close'].shift(-days) - df['Close']) / df['Close'] * 100
                    win_rate = (returns >= 10).sum() / returns.count() * 100 # 10天漲10%之機率
                    
                    if win_rate >= 40: # 基本門檻
                        res.append({"代號": code, "名稱": name, "現價": price, "歷史勝率%": round(win_rate, 2)})
                except: continue
            
            st.session_state.scan_results = pd.DataFrame(res)
            status.success(f"完成！共篩出 {len(res)} 檔高勝率標的。")
        except Exception as e: st.error(f"掃描出錯: {e}")

    if st.session_state.get('scan_results') is not None:
        st.subheader("🔍 二次深度評測結果")
        # 顯示最初版本之建議：進場、停損、停利
        df_eval = st.session_state.scan_results.copy()
        df_eval['🛡️ 停損價'] = (df_eval['現價'] * 0.95).round(2)
        df_eval['🎯 第一停利'] = (df_eval['現價'] * 1.10).round(2)
        st.dataframe(df_eval, use_container_width=True)

# --- [C] 庫存管理 (直接刪除機制回歸) ---
elif page == "➕ 庫存管理":
    st.header("➕ 庫存與金流精確校正")
    for idx, s in enumerate(st.session_state.portfolio):
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            col1.write(f"**{s['name']}** ({s['code']}) | 成本: {s['cost']:.2f}")
            actual_p = col2.number_input(f"手動賣出價", key=f"ap_{idx}", value=s['cost'], format="%.2f")
            
            if col3.button("賣出結帳", key=f"sell_{idx}"):
                st.session_state.current_cash += round(actual_p * s['shares'] * (1-FEE_RATE-0.003), 2)
                st.session_state.portfolio.pop(idx)
                st.rerun()
            
            # [功能回歸] 直接刪除存股機制
            if col4.button("🗑️ 直接刪除", key=f"del_{idx}"):
                st.session_state.portfolio.pop(idx)
                st.rerun()
