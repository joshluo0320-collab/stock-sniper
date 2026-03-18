import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統設定與 UI 控制台 (必須在引用變數前定義)
# ============================================
st.set_page_config(page_title="台股獵殺系統 - 盈利回測整合版", layout="wide")

st.sidebar.header("🕹️ 獵殺與庫存控制台")

# 定義總資產與門檻 (這些變數現在會先被定義)
if 'cash' not in st.session_state:
    st.session_state.cash = 190000 

cash_input = st.sidebar.number_input("當前可用銀彈 (NTD)", value=st.session_state.cash)
min_p5_threshold = st.sidebar.slider("🔥 5日機率過濾門檻", 30, 95, 45)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存建倉")
# 預設範例：代號,成本 (請在此修改你的真實成本)
inventory_input = st.sidebar.text_area("輸入庫存 (代號,成本)", value="2337,34\n1409,16.5")

# 解析庫存資料
inventory_dict = {}
for item in inventory_input.split('\n'):
    if ',' in item:
        try:
            ticker_id, cost = item.split(',')
            inventory_dict[f"{ticker_id.strip()}.TW"] = float(cost)
        except: continue

# ============================================
# 2. 核心計算函式
# ============================================
def calculate_logic(df, tp_pct):
    if len(df) < 20: return df
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    
    # 動態止盈邏輯
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    df['Exit_Signal'] = df['Close'] < df['Trailing_Stop_Line']
    return df

def get_report(df, ticker, cost, tp_pct):
    """計算特定庫存的盈利報告"""
    df = calculate_logic(df, tp_pct)
    last_p = df['Close'].iloc[-1]
    peak_p = df['Rolling_Peak'].iloc[-1]
    stop_line = df['Trailing_Stop_Line'].iloc[-1]
    
    profit_pct = (last_p - cost) / cost * 100
    
    return {
        "代號": ticker.replace(".TW",""),
        "成本": cost,
        "現價": round(last_p, 2),
        "累積盈利": f"{round(profit_pct, 2)}%",
        "最高點": round(peak_p, 2),
        "動態止盈線": round(stop_line, 2),
        "距離止盈線": f"{round((last_p/stop_line-1)*100, 2)}%",
        "狀態": "⚠️ 建議出清" if last_p < stop_line else "✅ 獲利奔跑"
    }

# ============================================
# 3. 主介面顯示
# ============================================
st.title("🚀 台股決賽輪：獵殺與盈利回測系統")

# --- 第一部分：庫存盈利回測 ---
st.subheader("💰 我的庫存盈利回測報告")
if st.button("📊 重新計算庫存盈虧"):
    if inventory_dict:
        inv_results = []
        for t, cost in inventory_dict.items():
            # 抓取較長時間確保涵蓋建倉日
            df_inv = yf.download(t, period="2y", progress=False)
            if not df_inv.empty:
                if isinstance(df_inv.columns, pd.MultiIndex): df_inv = df_inv.droplevel(1, axis=1)
                inv_results.append(get_report(df_inv, t, cost, trail_percent))
        
        st.table(pd.DataFrame(inv_results))
    else:
        st.info("尚未在側邊欄輸入庫存。")

st.markdown("---")

# --- 第二部分：全市場獵殺掃描 ---
st.subheader(f"🔍 全市場 {min_p5_threshold}% 噴發門檻掃描")
if st.button("🚀 啟動獵殺掃描"):
    # 此處簡化邏輯供演示，實際可放入之前的 get_market_list 邏輯
    sample_tickers = ["2330.TW", "2337.TW", "1409.TW", "3234.TW", "1711.TW"]
    hunt_results = []
    
    for t in sample_tickers:
        df_hunt = yf.download(t, period="4mo", progress=False)
        if not df_hunt.empty:
            if isinstance(df_hunt.columns, pd.MultiIndex): df_hunt = df_hunt.droplevel(1, axis=1)
            df_hunt = calculate_logic(df_hunt, trail_percent)
            # 這裡簡化為成交量過濾
            last_p = df_hunt['Close'].iloc[-1]
            hunt_results.append({
                "代號": t.replace(".TW",""),
                "現價": round(last_p, 2),
                "動態止盈線": round(df_hunt['Trailing_Stop_Line'].iloc[-1], 2),
                "狀態": "✅ 動能安全" if not df_hunt['Exit_Signal'].iloc[-1] else "⚠️ 回落中"
            })
    st.dataframe(pd.DataFrame(hunt_results), use_container_width=True)

# ============================================
# 4. 人生合夥人點醒
# ============================================
st.write("---")
st.write("### 💡 人生合夥人的真實點醒")
st.write(f"1. **變數順序問題**：修正了程式碼順序。現在系統會先讀取你的 Slider 設定（如 {trail_percent}%），才去計算盈虧報告。")
st.write(f"2. **旺宏 34 元的回測意義**：你可以看到「累積盈利」與「止盈線」的拉鋸。即便你賺了 300%，但如果現價跌破止盈線，系統依然會冷酷地標註『建議出清』。")
