import streamlit as st
import yfinance as yf
import pandas as pd

# ==========================================
# 1. 核心系統設定 & 狀態初始化
# ==========================================
st.set_page_config(page_title="Josh 的股市戰情室", page_icon="🦅", layout="wide")

# 初始化 session_state
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000},
        {"code": "8021", "name": "尖點", "cost": 239.0, "shares": 200}
    ]

# ==========================================
# 2. 核心函數：智能股價抓取 (含週一/假日修復)
# ==========================================
def get_smart_stock_data(ticker_code):
    """
    抓取庫存用的簡單報價 (回溯5天)
    """
    code = str(ticker_code)
    if not code.endswith('.TW') and not code.endswith('.TWO'):
        full_ticker = f"{code}.TW"
    else:
        full_ticker = code

    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="5d") # 抓5天避開假日
        if df.empty: return None

        last_row = df.iloc[-1]
        return {
            "code": code,
            "price": last_row['Close'],
            "change": last_row['Close'] - df.iloc[-2]['Close'] if len(df) >= 2 else 0,
            "pct_change": (last_row['Close'] - df.iloc[-2]['Close']) / df.iloc[-2]['Close'] * 100 if len(df) >= 2 else 0,
            "date": df.index[-1].strftime('%Y-%m-%d'),
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
    st.markdown("""
    **內建策略邏輯：**
    1. **多頭排列**：股價 > MA5 > MA20
    2. **強勢整理**：收盤價 >= (近60日最高價 * 0.95)
    3. **動能充足**：成交量 > 500 張
    """)
    
    # 這裡提供一個預設掃描清單 (模擬您的自選池)
    default_list = "2330, 2317, 2454, 2337, 4916, 8021, 3231, 2603, 2609, 2615"
    target_codes = st.text_area("輸入掃描代號 (用逗號分隔)", value=default_list)
    
    if st.button("🚀 執行掃描 (Josh 戰法)"):
        stock_list = [x.strip() for x in target_codes.split(",")]
        results = []
        progress_bar = st.progress(0)
        
        status_text = st.empty()
        
        for i, code in enumerate(stock_list):
            status_text.text(f"正在分析：{code} ...")
            progress_bar.progress((i + 1) / len(stock_list))
            
            # 處理代號
            if not code.endswith('.TW'): full_code = f"{code}.TW"
            else: full_code = code
            
            try:
                # 抓取足夠的歷史資料來算 MA 和 High60
                stock = yf.Ticker(full_code)
                df = stock.history(period="3mo") # 抓3個月
                
                if len(df) >= 60:
                    current = df.iloc[-1]
                    price = current['Close']
                    vol = current['Volume']
                    
                    # --- 核心邏輯計算 ---
                    ma5 = df['Close'].rolling(window=5).mean().iloc[-1]
                    ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                    high60 = df['High'].rolling(window=60).max().iloc[-1]
                    
                    # --- 條件判斷 ---
                    # 條件 1: 均線多頭 (MA5 > MA20) 且 站上 MA5
                    cond_trend = (price > ma5) and (ma5 > ma20)
                    
                    # 條件 2: 位置 (high60 * 0.95) -> 這是您原本過濾 4916 的條件
                    cond_pos = price >= (high60 * 0.95)
                    
                    # 條件 3: 成交量
                    cond_vol = vol > 500000 # 500張 (yfinance 單位是股)
                    
                    if cond_trend and cond_pos and cond_vol:
                        status = "✅ 符合"
                    elif not cond_pos:
                        status = "❌ 位置過低 (假突破濾網)"
                    elif not cond_trend:
                        status = "❌ 均線未排列"
                    else:
                        status = "❌ 量能不足"
                        
                    results.append({
                        "代號": code,
                        "現價": f"{price:.2f}",
                        "MA5": f"{ma5:.2f}",
                        "High60": f"{high60:.2f}",
                        "結果": status
                    })
            except:
                pass
        
        status_text.text("掃描完成！")
        progress_bar.empty()
        
        # 顯示結果表格
        if results:
            res_df = pd.DataFrame(results)
            
            # 樣式優化：符合的標紅字
            def highlight_row(row):
                return ['background-color: #d4edda; color: green' if "✅" in row['結果'] else '' for _ in row]

            st.dataframe(res_df.style.apply(highlight_row, axis=1))
        else:
            st.warning("沒有找到資料")

def page_management():
    st.header("➕ 庫存管理")
    
    with st.form("add_stock_form"):
        c1, c2, c3 = st.columns(3)
        new_code = c1.text_input("股票代號")
        new_name = c2.text_input("股票名稱")
        new_shares = c3.number_input("持有股數", min_value=1, value=1000)
        new_cost = st.number_input("平均成本", min_value=0.0, value=100.0)
        
        if st.form_submit_button("新增"):
            st.session_state.portfolio.append({
                "code": new_code, "name": new_name, "cost": new_cost, "shares": new_shares
            })
            st.success(f"已新增 {new_name}")

    st.subheader("📋 庫存清單")
    if len(st.session_state.portfolio) > 0:
        df_port = pd.DataFrame(st.session_state.portfolio)
        st.dataframe(df_port)
        
        del_idx = st.number_input("刪除索引 (Index)", min_value=0, max_value=len(st.session_state.portfolio)-1, step=1)
        if st.button("🗑️ 刪除"):
            st.session_state.portfolio.pop(del_idx)
            st.experimental_rerun()

# ==========================================
# 4. 主程式入口
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室導航")
    page = st.sidebar.radio("功能：", ["📊 庫存戰術看板", "🎯 狙擊選股掃描", "➕ 庫存管理"])
    st.sidebar.markdown("---")
    st.sidebar.info("已啟用週一自動回溯機制。")

    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "🎯 狙擊選股掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__":
    main()
