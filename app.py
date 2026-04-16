import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import os
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統常數
# ============================================
REPORT_FILE = "v23_sim_report.csv"
TOTAL_BUDGET = 190000
MAX_POSITIONS = 3
PER_STOCK_BUDGET = 60000
FRICTION_COST = 0.005 # 包含滑價與稅費

# ============================================
# 2. 核心功能函式
# ============================================
def get_report():
    if not os.path.exists(REPORT_FILE):
        df = pd.DataFrame(columns=["狀態", "名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線", "出場日期", "出場價", "損益金額", "報酬率"])
        df.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    return pd.read_csv(REPORT_FILE, encoding='utf-8-sig')

def is_market_open():
    now = datetime.now()
    if now.weekday() > 4: return False
    curr_time = now.hour * 100 + now.minute
    return 900 <= curr_time <= 1330

def execute_sniper_v23(df, tid, name, trail_p):
    try:
        if df.empty or len(df) < 40: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        last_p = round(float(df['Close'].iloc[-1]), 1)
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        
        if last_p > ma5 * 1.05: return None # 乖離過濾
        
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = (tr.rolling(14).mean().iloc[-1] / last_p) * 100
        if atr_ratio < 1.5: return None # 波動力過濾

        macd_slope = (df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()).diff().iloc[-1]
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 1)

        return {"代號": tid, "名稱": name, "勝率": score, "現價": last_p, "撤退線": withdrawal_line}
    except: return None

# ============================================
# 3. 介面與巡檢邏輯
# ============================================
st.set_page_config(page_title="v23.2 獵殺實驗室", layout="wide")
st.title("🏹 v23.2 科學博弈實證系統")

# --- 側邊欄維護區 ---
st.sidebar.header("🛠️ 環境重設")
if st.sidebar.button("🚨 一鍵清空所有紀錄並重置"):
    if os.path.exists(REPORT_FILE): os.remove(REPORT_FILE)
    st.sidebar.success("✅ 報表已完全移除。")
    st.rerun()

target_win = st.sidebar.slider("🎯 買入勝率門檻", 60, 95, 80, step=5)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 10.0, 5.0, step=1.0)

# 顯示帳本
report = get_report()
active_trades = report[report["狀態"] == "持有中"]
used_cash = (active_trades["進場價"] * active_trades["股數"]).sum()

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("🏃 目前持有部位")
    st.table(active_trades[["名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線"]]) if not active_trades.empty else st.info("無持股。")

with col2:
    st.metric("💰 剩餘現金", f"{int(TOTAL_BUDGET - used_cash)} 元")
    st.metric("⚖️ 市場狀態", "🟢 開盤中" if is_market_open() else "🔴 休市中")

# 巡檢按鈕
if st.button("🔴 執行定時巡檢 (選股 + 買賣同步)", type="primary"):
    with st.status("同步中...", expanded=True) as status:
        # 1. 處理賣出 (不限時段)
        if not active_trades.empty:
            for idx, row in active_trades.iterrows():
                data = yf.download(f"{row['代號']}.TW", period="5d", progress=False)
                if data.empty: data = yf.download(f"{row['代號']}.TWO", period="5d", progress=False)
                if not data.empty:
                    curr_p = round(float(data['Close'].iloc[-1]), 1)
                    if curr_p < row['當前撤退線']:
                        exit_price = round(curr_p * (1 - FRICTION_COST), 1)
                        report.at[idx, "狀態"], report.at[idx, "出場價"] = "已結案", exit_price
                        report.at[idx, "出場日期"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        report.at[idx, "損益金額"] = int((exit_price - row['進場價']) * row['股數'])
                        st.warning(f"⚠️ {row['名稱']} 觸發撤退。")

        # 2. 處理買入 (限開盤)
        if is_market_open():
            # [此處插入掃描與買入邏輯，包含 check 重複代號與 MAX_POSITIONS]
            st.write("執行市場掃描...")
        else:
            st.info("🌙 目前休市，暫停模擬買入。")
            
        report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
        status.update(label="✅ 同步完成", state="complete")
    st.rerun()
