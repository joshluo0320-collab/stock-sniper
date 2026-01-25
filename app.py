import streamlit as st
import yfinance as yf
import pandas as pd

# ---------------------------------------------------------
# 🛠️ 核心函數：智能股價抓取 (解決週一/假日無數據問題)
# ---------------------------------------------------------
def get_smart_stock_data(ticker_code):
    """
    抓取最新股價，邏輯：
    1. 不抓 '1d' (今天)，改抓 '5d' (過去5天)。
    2. 自動取 'iloc[-1]' (最後一筆)，無論是週五還是今天，保證有數據。
    3. 計算漲跌幅 (與前一日收盤比較)。
    """
    # 1. 自動補上台股代號後綴 (預設為上市 .TW)
    # 如果您有上櫃股票(如部分生技股)，可能需要改為 .TWO，這裡先統一用 .TW
    if not str(ticker_code).endswith('.TW') and not str(ticker_code).endswith('.TWO'):
        full_ticker = f"{ticker_code}.TW"
    else:
        full_ticker = ticker_code

    try:
        # 2. 抓取過去 5 天的歷史資料 (關鍵修正！)
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="5d")
        
        # 如果抓不到資料 (例如代號錯誤)
        if df.empty:
            return None

        # 3. 鎖定「最後一筆」有效數據 (Latest Close)
        last_row = df.iloc[-1]
        latest_price = last_row['Close']
        latest_date = df.index[-1].strftime('%Y-%m-%d') # 格式化日期
        
        # 4. 計算漲跌 (用最後一筆 vs 倒數第二筆)
        if len(df) >= 2:
            prev_close = df.iloc[-2]['Close']
            change = latest_price - prev_close
            pct_change = (change / prev_close) * 100
        else:
            change = 0.0
            pct_change = 0.0

        return {
            "code": ticker_code,
            "price": latest_price,
            "change": change,
            "pct_change": pct_change,
            "date": latest_date,
            "valid": True
        }

    except Exception as e:
        return None

# ---------------------------------------------------------
# 📱 前端介面：庫存戰術看板 (Streamlit UI)
# ---------------------------------------------------------

st.title("🦅 Josh 的股市狙擊手戰情室")
st.subheader("🛡️ 庫存戰術看板 (24H 顯示版)")

# 模擬您的庫存清單 (您可以連接到您的資料庫或 Excel)
my_portfolio = [
    {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
    {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000},
    {"code": "8021", "name": "尖點", "cost": 239.0, "shares": 200}
]

# 重新整理按鈕 (清除快取用)
if st.button("🔄 強制刷新報價"):
    st.cache_data.clear()

# 建立欄位佈局
cols = st.columns(len(my_portfolio))

for idx, stock in enumerate(my_portfolio):
    with cols[idx]:
        # 呼叫上面的智能函數
        data = get_smart_stock_data(stock["code"])
        
        if data and data["valid"]:
            # 計算未實現損益 (估算)
            market_value = data["price"] * stock["shares"]
            cost_value = stock["cost"] * stock["shares"]
            profit_loss = market_value - cost_value
            profit_pct = (profit_loss / cost_value) * 100
            
            # 決定顏色 (台股：紅漲綠跌)
            color_str = "normal"
            if data["change"] > 0: color_str = "off" # Streamlit metric 自動紅綠邏輯
            
            # 顯示數據卡片
            st.metric(
                label=f"{stock['name']} ({stock['code']})",
                value=f"{data['price']:.2f}",
                delta=f"{data['change']:.2f} ({data['pct_change']:.2f}%)"
            )
            
            # 顯示損益與資料日期 (關鍵：讓您知道這是哪一天的價錢)
            st.caption(f"資料日期: {data['date']}")
            
            # 損益顯示
            if profit_loss > 0:
                st.markdown(f":red[獲利: +{int(profit_loss):,} (+{profit_pct:.1f}%)]")
            else:
                st.markdown(f":green[虧損: {int(profit_loss):,} ({profit_pct:.1f}%)]")
                
        else:
            st.error(f"{stock['name']} 讀取失敗")

st.markdown("---")
st.info("💡 提示：此系統已啟用「智能回溯」機制。即使在週一凌晨或假日，也能顯示最後一筆有效收盤價，不會再顯示空白。")
