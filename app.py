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
# 1. 系統參數與初始化
# ============================================
TOTAL_BUDGET = 190000
MAX_POSITIONS = 3
PER_STOCK_BUDGET = 60000
FRICTION_COST = 0.005
REPORT_FILE = "v23_sim_report.csv"

def get_report():
    if not os.path.exists(REPORT_FILE):
        df = pd.DataFrame(columns=["狀態", "名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線", "出場日期", "出場價", "損益金額", "報酬率"])
        df.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    return pd.read_csv(REPORT_FILE, encoding='utf-8-sig')

# ============================================
# 2. 開盤時間檢查邏輯
# ============================================
def is_market_open():
    now = datetime.now()
    # 0:週一 ... 4:週五
    if now.weekday() > 4: return False
    current_time = now.hour * 100 + now.minute
    return 900 <= current_time <= 1330

# ============================================
# 3. 核心獵殺邏輯 (v23.2)
# ============================================
def execute_sniper_v23(df, tid, name, trail_p):
    try:
        if df.empty or len(df) < 40: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        last_p = round(float(df['Close'].iloc[-1]), 1)
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        
        # 佛系過濾：乖離 > 5% 不追
        if last_p > ma5 * 1.05: return None 

        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = (tr.rolling(14).mean().iloc[-1] / last_p) * 100
        if atr_ratio < 1.5: return None

        macd_slope = (df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()).diff().iloc[-1]
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 1)

        return {"代號": tid, "名稱": name, "勝率": score, "現價": last_p, "撤退線": withdrawal_line, "ATR": atr_ratio}
    except: return None

# ============================================
# 4. Streamlit UI 與自動化同步
# ============================================
st.set_page_config(page_title="v23.2 模擬實證實驗室", layout="wide")
st.title("🏹 v23.2 科學博弈實證系統 (安全防護版)")

report = get_report()
active_trades = report[report["狀態"] == "持有中"]
closed_trades = report[report["狀態"] == "已結案"]

# 顯示目前狀態
st.sidebar.header("🕹️ 實驗參數")
target_win = st.sidebar.slider("🎯 買入勝率門檻", 60, 95, 80, step=5)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 10.0, 5.0, step=1.0)

# 手動修正功能 (放在側邊欄，預防萬一)
if st.sidebar.button("🧹 清除異常重複持股"):
    report = report.drop_duplicates(subset=['代號', '狀態'], keep='first')
    report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("重複項已清理")

# --- UI 佈局 ---
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("🏃 當前持有部位")
    if not active_trades.empty:
        st.table(active_trades[["名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線"]])
    else:
        st.info("目前無持有部位。")

with col2:
    current_cash = TOTAL_BUDGET - (active_trades["進場價"] * active_trades["股數"]).sum()
    st.metric("💰 剩餘現金", f"{int(current_cash)} 元")
    st.metric("⚖️ 市場狀態", "🟢 開盤中" if is_market_open() else "🔴 休市中")

# --- 一鍵同步按鈕 ---
if st.button("🔴 執行定時巡檢 (選股 + 買賣同步)", type="primary"):
    with st.status("正在同步報表與掃描...", expanded=True) as status:
        # 1. 檢查賣出 (審判)
        if not active_trades.empty:
            for idx, row in active_trades.iterrows():
                suffix = ".TW" if len(str(row['代號'])) == 4 else ""
                data = yf.download(f"{row['代號']}{suffix}", period="5d", progress=False)
                if not data.empty:
                    curr_p = round(float(data['Close'].iloc[-1]), 1)
                    if curr_p < row['當前撤退線']:
                        exit_price = round(curr_p * (1 - FRICTION_COST), 1)
                        p_l = (exit_price - row['進場價']) * row['股數']
                        report.at[idx, "狀態"] = "已結案"
                        report.at[idx, "出場日期"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        report.at[idx, "出場價"] = exit_price
                        report.at[idx, "損益金額"] = int(p_l)
                        report.at[idx, "報酬率"] = f"{round((exit_price/row['進場價']-1)*100, 2)}%"
                        st.warning(f"⚠️ {row['名稱']} 已撤退！")

        # 2. 檢查買入 (僅在開盤時間)
        if is_market_open():
            if len(report[report["狀態"] == "持有中"]) < MAX_POSITIONS:
                # 取得市場名單 (此處調用前述 get_market_map)
                from_tickers, names_map = get_market_map()
                # 掃描邏輯 (簡化示意)
                # ... (執行 execute_sniper_v23)
                # 重要：買入前比對 report[report["狀態"] == "持有中"]["代號"]
                # if pick['代號'] not in active_trades['代號'].values:
                #     執行模擬買入...
                pass
        else:
            st.info("🌙 目前非交易時段，僅執行庫存結算，不進行新獵物買入。")
            
        report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
        status.update(label="✅ 同步完成", state="complete")
    st.rerun()
