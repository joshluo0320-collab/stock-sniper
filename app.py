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
# 1. 系統參數 (19 萬科學博弈)
# ============================================
TOTAL_BUDGET = 190000
MAX_POSITIONS = 3
PER_STOCK_BUDGET = 60000
FRICTION_COST = 0.005  # 交易摩擦成本 0.5%
REPORT_FILE = "v23_sim_report.csv"

def get_report():
    if not os.path.exists(REPORT_FILE):
        df = pd.DataFrame(columns=["狀態", "名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線", "出場日期", "出場價", "損益金額", "報酬率"])
        df.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    return pd.read_csv(REPORT_FILE, encoding='utf-8-sig')

# ============================================
# 2. 安全檢查與時段鎖定
# ============================================
def is_market_open():
    now = datetime.now()
    if now.weekday() > 4: return False  # 週六日不開盤
    current_time = now.hour * 100 + now.minute
    return 900 <= current_time <= 1330  # 台股開盤時段

# ============================================
# 3. 核心獵殺邏輯 (v23.2 佛系優化版)
# ============================================
def execute_sniper_v23(df, tid, name, trail_p):
    try:
        if df.empty or len(df) < 40: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        last_p = round(float(df['Close'].iloc[-1]), 1)
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        
        # 佛系過濾：乖離 > 5% 不追
        if last_p > ma5 * 1.05: return None 
        
        # ATR 波動力
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = (tr.rolling(14).mean().iloc[-1] / last_p) * 100
        if atr_ratio < 1.5: return None

        macd_slope = (df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()).diff().iloc[-1]
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 1)

        return {"代號": tid, "名稱": name, "勝率": score, "現價": last_p, "撤退線": withdrawal_line}
    except: return None

# ============================================
# 4. Streamlit UI 戰略中樞
# ============================================
st.set_page_config(page_title="v23.2 實證實驗室", layout="wide")
st.title("🏹 v23.2 科學博弈實證系統")

report = get_report()
active_trades = report[report["狀態"] == "持有中"]
closed_trades = report[report["狀態"] == "已結案"]

# --- 側邊欄：維護與清理工具 ---
st.sidebar.header("🛠️ 實驗維護區")
if st.sidebar.button("🧹 清空所有『持有中』部位 (重置資金)"):
    # 保留已結案的紀錄，僅刪除持有中的資料
    report = report[report["狀態"] == "已結案"]
    report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("持有部位已清空，19 萬資金已歸位。")
    st.rerun()

st.sidebar.markdown("---")
target_win = st.sidebar.slider("🎯 買入勝率門檻", 60, 95, 80, step=5)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 10.0, 5.0, step=1.0)

# --- UI 佈局 ---
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("🏃 當前持有部位")
    if not active_trades.empty:
        st.table(active_trades[["名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線"]])
    else:
        st.info("目前無持有部位，19 萬資金待命。")

with col2:
    used_cash = (active_trades["進場價"] * active_trades["股數"]).sum()
    st.metric("💰 剩餘可用現金", f"{int(TOTAL_BUDGET - used_cash)} 元")
    st.metric("⚖️ 市場狀態", "🟢 開盤中" if is_market_open() else "🔴 休市中")

# --- 執行按鈕 ---
if st.button("🔴 執行定時巡檢 (選股 + 買賣同步)", type="primary"):
    with st.status("執行中...", expanded=True) as status:
        # 1. 先處理賣出 (不論開休市皆可結算)
        if not active_trades.empty:
            for idx, row in active_trades.iterrows():
                # (此處執行賣出邏輯，略，同前版內容)
                pass

        # 2. 再處理買入 (嚴格限制開盤時間)
        if is_market_open():
            if len(report[report["狀態"] == "持有中"]) < MAX_POSITIONS:
                # (此處執行選股與買入邏輯，略，同前版內容)
                # 重要：買入前會檢查 if pick['代號'] not in active_trades['代號'].values 避免重複購買
                pass
        else:
            st.info("🌙 目前為休市時間。系統僅更新庫存數據，暫停『模擬買入』功能。")
        
        report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
        status.update(label="✅ 同步完成", state="complete")
    st.rerun()

if not closed_trades.empty:
    st.divider()
    st.subheader("📈 已結案歷史戰績")
    st.table(closed_trades)
