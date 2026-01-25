import streamlit as st
import yfinance as yf
import pandas as pd

# ==========================================
# 1. 核心系統設定 & 狀態初始化
# ==========================================
st.set_page_config(page_title="Josh 的股市戰情室", page_icon="🦅", layout="wide")

# 初始化 session_state 用來存儲「庫存清單」
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000},
        {"code": "8021", "name": "尖點", "cost": 239.0, "shares": 200}
    ]

# ==========================================
# 2. 核心函數：智能股價抓取 (含週一修復邏輯)
# ==========================================
def get_smart_stock_data(ticker_code):
    if not str(ticker_code).endswith('.TW') and not str(ticker_code).endswith('.TWO'):
        full_ticker = f"{ticker_code}.TW"
    else:
        full_ticker = ticker_code

    try:
        # 關鍵修復：抓取 5 天資料，確保假日也能顯示上週五收盤價
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="5d")
        
        if df.empty: return None

        last_row = df.iloc[-1]
        latest_price = last_row['Close']
        latest_date = df.index[-1].strftime('%Y-%m-%d')
        
        if len(df) >= 2:
            prev_close = df.iloc[-2]['Close']
            change = latest_price - prev_close
            pct_change = (change / prev_close) * 100
        else:
            change, pct_change = 0.0, 0.0

        return {
            "code": ticker_code,
            "price": latest_price,
            "change": change,
            "pct_change": pct_change,
            "date": latest_date,
            "valid": True
        }
    except:
        return None

# ==========================================
# 3. 介面功能模組
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板")
    st.info(f"目前監控庫存數：{len(st.session_state.portfolio)} 檔")
    
    if st.button("🔄 刷新報價"):
        st.cache_data.clear()

    cols = st.columns(3)
    for i, stock in enumerate(st.session_state.portfolio):
        col = cols[i % 3]
        with col:
            data = get_smart_stock_data(stock["code"])
            if data:
                market_val = data["price"] * stock["shares"]
                cost_val = stock["cost"] * stock["shares"]
                profit = market_val - cost_val
                profit_pct = (profit / cost_val) * 100 if cost_val != 0 else 0
                
                st.metric(
                    label=f"{stock['name']} ({stock['code']})",
                    value=f"{data['price']:.2f}",
                    delta=f"{data['change']:.2f} ({data['pct_change']:.2f}%)"
                )
                if profit > 0:
                    st.markdown(f"💰 :red[+{int(profit):,} (+{profit_pct:.1f}%)]")
                else:
                    st.markdown(f"💸 :green[{int(profit):,} ({profit_pct:.1f}%)]")
                st.caption(f"資料日期: {data['date']}")
                st.markdown("---")
            else:
                st.error(f"{stock['name']} 讀取失敗")

def page_scanner():
    st.header("🎯 狙擊選股掃描")
    
    # --- 這裡是用戶原本的選股邏輯區 ---
    # 移除了警告文字和選擇策略的下拉選單
    
    # 保留一個簡單的參數輸入 (如果您不需要也可以刪除)
    threshold = st.number_input("篩選股價門檻 (>)", value=10, step=1)
    
    if st.button("🚀 開始掃描"):
        st.write("正在執行掃描邏輯...")
        
        # [請在此處貼回您原本的 for 迴圈或篩選程式碼]
        # 下面是範例顯示，您可以直接把原本的邏輯寫在這裡
        
        # 範例結果
        st.success("掃描完成！(請在此處植入您的篩選邏輯)")
        st.dataframe(pd.DataFrame({
            "代號": ["2330"],
            "名稱": ["範例台積電"],
            "收盤": [1000],
            "訊號": ["符合條件"]
        }))
    # ---------------------------------------

def page_management():
    st.header("➕ 庫存管理")
    
    with st.form("add_stock_form"):
        c1, c2, c3 = st.columns(3)
        new_code = c1.text_input("股票代號 (如 2330)")
        new_name = c2.text_input("股票名稱 (如 台積電)")
        new_shares = c3.number_input("持有股數", min_value=1, value=1000)
        new_cost = st.number_input("平均成本", min_value=0.0, value=100.0)
        
        submitted = st.form_submit_button("新增至庫存")
        
        if submitted:
            if new_code and new_name:
                st.session_state.portfolio.append({
                    "code": new_code, 
                    "name": new_name, 
                    "cost": new_cost, 
                    "shares": new_shares
                })
                st.success(f"✅ 已新增 {new_name} ({new_code})")
            else:
                st.error("請輸入完整的代號與名稱")

    st.subheader("📋 目前監控清單")
    if len(st.session_state.portfolio) > 0:
        df_port = pd.DataFrame(st.session_state.portfolio)
        st.dataframe(df_port)
        
        del_idx = st.number_input("輸入要刪除的索引 (Index)", min_value=0, max_value=len(st.session_state.portfolio)-1, step=1)
        if st.button("🗑️ 刪除選定股票"):
            st.session_state.portfolio.pop(del_idx)
            st.experimental_rerun()

# ==========================================
# 4. 主程式入口 (側邊選單導航)
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室導航")
    
    # 側邊選單選項
    page = st.sidebar.radio(
        "前往功能：",
        ["📊 庫存戰術看板", "🎯 狙擊選股掃描", "➕ 庫存管理"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.info("💡 提示：系統已啟用週一自動回溯機制。")

    if page == "📊 庫存戰術看板":
        page_dashboard()
    elif page == "🎯 狙擊選股掃描":
        page_scanner()
    elif page == "➕ 庫存管理":
        page_management()

if __name__ == "__main__":
    main()
