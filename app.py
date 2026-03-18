import streamlit as st
import yfinance as yf
import pandas as pd

# ============================================
# 庫存回測模組 (Manual Inventory)
# ============================================
st.sidebar.header("📋 我的庫存建倉")
# 格式：代號,成本 (例如 2337,34)
inventory_input = st.sidebar.text_area("輸入庫存 (代號,成本)", value="2337,34\n1409,16.5")

inventory_dict = {}
for item in inventory_input.split('\n'):
    if ',' in item:
        ticker_id, cost = item.split(',')
        inventory_dict[f"{ticker_id.strip()}.TW"] = float(cost)

# ============================================
# 盈利回測與止盈邏輯
# ============================================
def backtest_profit(df, ticker, trail_percent):
    cost = inventory_dict.get(ticker)
    
    # 1. 抓取該標的所有歷史最高價 (不限三個月)
    df['Rolling_Peak'] = df['High'].cummax()
    
    # 2. 計算動態止盈線
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - trail_percent / 100)
    
    last_price = df['Close'].iloc[-1]
    peak_price = df['Rolling_Peak'].iloc[-1]
    
    # 3. 如果有建倉成本，計算盈利
    profit_pct = 0
    if cost:
        profit_pct = (last_price - cost) / cost * 100
        
    return {
        "現價": round(last_price, 2),
        "成本": cost if cost else "未持有",
        "累積漲幅": f"{round(profit_pct, 2)}%" if cost else "-",
        "最高價點位": round(peak_price, 2),
        "目前止盈線": round(df['Trailing_Stop_Line'].iloc[-1], 2),
        "狀態": "⚠️ 建議出清" if last_price < df['Trailing_Stop_Line'].iloc[-1] else "✅ 獲利奔跑中"
    }

# ============================================
# 主介面顯示 (回測報告)
# ============================================
st.title("💰 庫存盈利與動態止盈回測報告")

if st.button("📊 執行庫存盈虧回測"):
    if not inventory_dict:
        st.warning("請先在側邊欄輸入庫存資料。")
    else:
        results = []
        for t, cost in inventory_dict.items():
            # 抓取較長的時間跨度以確保抓到 34 元後的最高點
            df = yf.download(t, period="2y", progress=False) 
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(1, axis=1)
                report = backtest_profit(df, t, trail_percent) # trail_percent 來自側邊欄 slider
                report['代號'] = t.replace(".TW","")
                results.append(report)
        
        res_df = pd.DataFrame(results)
        st.table(res_df)
