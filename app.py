import streamlit as st
import yfinance as yf
import pandas as pd

# ==========================================
# 1. 核心系統設定 & 狀態初始化
# ==========================================
st.set_page_config(page_title="Josh 的股市戰情室", page_icon="🦅", layout="wide")

# 初始化庫存 (這裡模擬您的真實庫存)
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000},
        {"code": "8021", "name": "尖點", "cost": 239.0, "shares": 200}
    ]

# ==========================================
# 2. 核心函數：智能股價抓取
# ==========================================
def get_smart_stock_data(ticker_code):
    """
    抓取回溯 5 天的資料，確保週一或假日也能顯示上週收盤價
    """
    code = str(ticker_code)
    # 自動補上 .TW (如果沒有輸入的話)
    if not code.endswith('.TW') and not code.endswith('.TWO'):
        full_ticker = f"{code}.TW"
    else:
        full_ticker = code

    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="5d")
        
        if df.empty: return None

        # 抓取最後一筆有效資料
        last_row = df.iloc[-1]
        
        # 計算漲跌 (跟前一筆比)
        if len(df) >= 2:
            prev_close = df.iloc[-2]['Close']
            change = last_row['Close'] - prev_close
            pct_change = (change / prev_close) * 100
        else:
            change, pct_change = 0.0, 0.0

        return {
            "code": code,
            "price": last_row['Close'],
            "change": change,
            "pct_change": pct_change,
            "date": df.index[-1].strftime('%Y-%m-%d'),
            "valid": True
        }
    except:
        return None

# ==========================================
# 3. 戰術分析邏輯 (新功能 ✨)
# ==========================================
def generate_strategy_advice(profit_pct):
    """
    根據損益百分比，生成直觀的戰術建議文字
    """
    if profit_pct >= 10:
        return "🚀 **大獲全勝**：獲利已拉開，移動停利設好，讓獲利奔跑！"
    elif 5 <= profit_pct < 10:
        return "📈 **穩健獲利**：表現不錯，續抱觀察，不用急著賣。"
    elif 0 <= profit_pct < 5:
        return "🛡️ **成本保衛**：小賺或持平，密切觀察，跌破成本需警戒。"
    elif -5 < profit_pct < 0:
        return "⚠️ **警戒狀態**：小幅虧損，請檢查是否跌破支撐 (如MA5)。"
    else: # 虧損超過 5%
        return "🛑 **停損評估**：虧損擴大，請確認是否觸發停損紀律，嚴禁凹單！"

# ==========================================
# 4. 介面功能模組
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板")
    st.info(f"目前監控：{len(st.session_state.portfolio)} 檔股票")
    
    if st.button("🔄 刷新最新報價"):
        st.cache_data.clear()
        st.rerun()

    # 使用 3 欄排列
    cols = st.columns(3)
    
    for i, stock in enumerate(st.session_state.portfolio):
        col = cols[i % 3] # 讓卡片依序排列
        with col:
            # 1. 取得股價
            data = get_smart_stock_data(stock["code"])
            
            # 裝飾外框 (Container)
            with st.container(border=True):
                if data:
                    # 計算損益
                    market_val = data["price"] * stock["shares"]
                    cost_val = stock["cost"] * stock["shares"]
                    profit = market_val - cost_val
                    profit_pct = (profit / cost_val) * 100 if cost_val != 0 else 0
                    
                    # 標題與股價
                    st.subheader(f"{stock['name']} ({stock['code']})")
                    st.metric(
                        label=f"收盤 ({data['date']})",
                        value=f"{data['price']:.2f}",
                        delta=f"{data['change']:.2f} ({data['pct_change']:.2f}%)"
                    )
                    
                    # 損益顯示
                    if profit > 0:
                        st.markdown(f"**損益**： :red[+{int(profit):,} (+{profit_pct:.1f}%)]")
                    else:
                        st.markdown(f"**損益**： :green[{int(profit):,} ({profit_pct:.1f}%)]")
                    
                    st.divider() # 分隔線
                    
                    # 2. 新增：戰術建議文字
                    advice = generate_strategy_advice(profit_pct)
                    st.markdown(f"💡 {advice}")
                    
                    st.divider() # 分隔線

                    # 3. 新增：關鍵情報連結 (動態生成)
                    # 這裡利用 Google 和 Yahoo 的網址規則
                    yahoo_link = f"https://tw.stock.yahoo.com/quote/{stock['code']}"
                    google_news_link = f"https://www.google.com/search?q={stock['name']}+{stock['code']}+新聞&tbm=nws"
                    cm_money_link = f"https://www.cmoney.tw/forum/stock/{stock['code']}"
                    
                    st.markdown("🔎 **情報來源：**")
                    st.markdown(f"""
                    - [Yahoo 個股與新聞]({yahoo_link})
                    - [Google 最新新聞]({google_news_link})
                    - [股市同學會 (散戶氣氛)]({cm_money_link})
                    """)
                    
                else:
                    st.error(f"{stock['name']} 讀取失敗 (請檢查代號)")

def page_scanner():
    st.header("🎯 狙擊選股掃描")
    st.markdown("**(策略邏輯：MA多頭排列 + 假突破濾網 + 量能篩選)**")
    
    # 預設清單
    default_list = "2330, 2317, 2454, 2337, 4916, 8021, 2603"
    target_codes = st.text_area("輸入掃描代號 (逗號分隔)", value=default_list)
    
    if st.button("🚀 執行掃描 (Josh 戰法)"):
        stock_list = [x.strip() for x in target_codes.split(",")]
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, code in enumerate(stock_list):
            status_text.text(f"分析中：{code} ...")
            progress_bar.progress((i + 1) / len(stock_list))
            
            # 處理代號
            full_code = f"{code}.TW" if not code.endswith('.TW') else code
            
            try:
                # 抓 3 個月資料算技術指標
                stock = yf.Ticker(full_code)
                df = stock.history(period="3mo")
                
                if len(df) >= 60:
                    current = df.iloc[-1]
                    price = current['Close']
                    vol = current['Volume']
                    
                    # 技術指標
                    ma5 = df['Close'].rolling(5).mean().iloc[-1]
                    ma20 = df['Close'].rolling(20).mean().iloc[-1]
                    high60 = df['High'].rolling(60).max().iloc[-1]
                    
                    # 策略邏輯
                    cond_trend = (price > ma5) and (ma5 > ma20)
                    cond_pos = price >= (high60 * 0.95)
                    cond_vol = vol > 500000 # 500張
                    
                    if cond_trend and cond_pos and cond_vol:
                        status = "✅ 符合"
                    elif not cond_pos:
                        status = "❌ 位置過低"
                    elif not cond_trend:
                        status = "❌ 均線未排列"
                    else:
                        status = "❌ 量能不足"
                        
                    results.append({
                        "代號": code,
                        "現價": f"{price:.2f}",
                        "結果": status,
                        "MA5": f"{ma5:.2f}",
                        "High60": f"{high60:.2f}"
                    })
            except:
                pass
        
        status_text.text("掃描完成！")
        progress_bar.empty()
        
        if results:
            res_df = pd.DataFrame(results)
            # 樣式：符合的整行標示淺綠色
            def highlight_row(row):
                return ['background-color: #d4edda; color: green' if "✅" in row['結果'] else '' for _ in row]
            st.dataframe(res_df.style.apply(highlight_row, axis=1))
        else:
            st.warning("沒有抓到資料")

def page_management():
    st.header("➕ 庫存管理")
    
    with st.form("add_stock"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("股票代號")
        name = c2.text_input("股票名稱")
        shares = c3.number_input("持有股數", value=1000)
        cost = st.number_input("平均成本", value=100.0)
        
        if st.form_submit_button("新增"):
            st.session_state.portfolio.append({
                "code": code, "name": name, "cost": cost, "shares": shares
            })
            st.success(f"已新增 {name}")

    st.subheader("📋 庫存列表")
    if st.session_state.portfolio:
        df = pd.DataFrame(st.session_state.portfolio)
        st.dataframe(df)
        
        idx = st.number_input("刪除索引", min_value=0, max_value=len(st.session_state.portfolio)-1, step=1)
        if st.button("🗑️ 刪除"):
            st.session_state.portfolio.pop(idx)
            st.rerun()

# ==========================================
# 5. 主程式入口
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室導航")
    page = st.sidebar.radio("功能選單", ["📊 庫存戰術看板", "🎯 狙擊選股掃描", "➕ 庫存管理"])
    st.sidebar.markdown("---")
    st.sidebar.caption("v3.0 智能增強版")

    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "🎯 狙擊選股掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__":
    main()
