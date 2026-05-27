import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
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

def get_market_map():
    # 實證名單
    tickers = ["2352.TW", "2886.TW", "0052.TW", "2317.TW"]
    names_map = {"2352.TW": "佳世達", "2886.TW": "兆豐金", "0052.TW": "富邦科技", "2317.TW": "鴻海"}
    return tickers, names_map

# ============================================
# 2. 開盤時間檢查邏輯 (僅用於顯示 UI 狀態與限制進場時間戳記)
# ============================================
def is_market_open():
    now = datetime.now()
    if now.weekday() > 4: return False
    current_time = now.hour * 100 + now.minute
    return 900 <= current_time <= 1330

# ============================================
# 3. 核心獵殺邏輯 (v23.3 主升段優化)
# ============================================
def execute_sniper_v23_3(df, tid, name, trail_p):
    try:
        if df.empty or len(df) < 40: return None
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        last_p = round(float(df['Close'].iloc[-1]), 1)
        
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma10 = df['Close'].rolling(10).mean().iloc[-1]
        
        # 偏離 10MA 超過 8% 才攔截
        if last_p > ma10 * 1.08: return None 

        # ATR 波動力濾網
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = (tr.rolling(14).mean().iloc[-1] / last_p) * 100
        if atr_ratio < 1.5: return None

        # 動能斜率與20日突破
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_slope = macd_line.diff().iloc[-1]
        
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        
        # 計分公式
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 1)

        return {"代號": tid, "名稱": name, "勝率": score, "現價": last_p, "撤退線": withdrawal_line, "ATR": atr_ratio}
    except: 
        return None

# ============================================
# 4. Streamlit UI
# ============================================
st.set_page_config(page_title="v23.3 模擬實證實驗室", layout="wide")
st.title("🏹 v23.3 科學博弈實證系統 (主升段解鎖版)")

report = get_report()
active_trades = report[report["狀態"] == "持有中"]
closed_trades = report[report["狀態"] == "已結案"]

# 側邊欄參數
st.sidebar.header("🕹️ 實驗參數 (v23.3)")
target_win = st.sidebar.slider("🎯 買入勝率門檻", 60, 95, 80, step=5)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 10.0, 5.0, step=1.0)

if st.sidebar.button("🧹 清除異常重複持股"):
    report = report.drop_duplicates(subset=['代號', '狀態'], keep='first')
    report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("重複項已清理")
    st.rerun()

# 佈局顯示
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
    
    # 增加測試模式提示
    market_status = is_market_open()
    st.metric("⚖️ 市場狀態", "🟢 開盤中" if market_status else "🔴 休市中 (測試模式解鎖)")

# ============================================
# 5. 一鍵巡檢與同步自動化 (已移除休市限制)
# ============================================
if st.button("🔴 執行定時巡檢 (選股 + 買賣同步)", type="primary"):
    with st.status("正在同步報表與掃描...", expanded=True) as status:
        
        # 【SOP 1】檢查賣出 (無論開休市皆進行最新收盤價盤後清算)
        if not active_trades.empty:
            for idx, row in active_trades.iterrows():
                data = yf.download(row['代號'], period="5d", progress=False)
                if not data.empty:
                    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
                    curr_p = round(float(data['Close'].iloc[-1]), 1)
                    
                    if curr_p < row['當前撤退線']:
                        exit_price = round(curr_p * (1 - FRICTION_COST), 1)
                        p_l = (exit_price - row['進場價']) * row['股數']
                        report.at[idx, "狀態"] = "已結案"
                        report.at[idx, "出場日期"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        report.at[idx, "出場價"] = exit_price
                        report.at[idx, "損益金額"] = int(p_l)
                        report.at[idx, "報酬率"] = f"{round((exit_price/row['進場價']-1)*100, 2)}%"
                        st.warning(f"⚠️ {row['名稱']} ({row['代號']}) 已跌破撤退線，執行強制撤退！")

        # 【SOP 2】檢查買入 (已解鎖：休市時以最後收盤價進行模擬買入測試)
        current_active_count = len(report[report["狀態"] == "持有中"])
        if current_active_count < MAX_POSITIONS:
            tickers, names_map = get_market_map()
            
            for ticker in tickers:
                if ticker in report[report["狀態"] == "持有中"]["代號"].values:
                    continue
                    
                if current_active_count >= MAX_POSITIONS:
                    break
                    
                hist_data = yf.download(ticker, period="60d", progress=False)
                pick = execute_sniper_v23_3(hist_data, ticker, names_map[ticker], trail_pct)
                
                if pick and pick["勝率"] >= target_win:
                    shares = int(PER_STOCK_BUDGET / (pick["現價"] * (1 + FRICTION_COST)))
                    if shares > 0:
                        entry_p = round(pick["現價"] * (1 + FRICTION_COST), 1)
                        
                        # 標註進場時間（若休市則標註盤後測試）
                        time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        if not market_status:
                            time_str += " (盤後測試)"
                            
                        new_trade = pd.DataFrame([{
                            "狀態": "持有中", "名稱": pick["名稱"], "代號": pick["代號"],
                            "進場日期": time_str,
                            "進場價": entry_p, "股數": shares, "當前撤退線": pick["撤退線"],
                            "出場日期": np.nan, "出場價": np.nan, "損益金額": 0, "報酬率": "0.0%"
                        }])
                        report = pd.concat([report, new_trade], ignore_index=True)
                        current_active_count += 1
                        st.success(f"🏹 獵殺成功！v23.3 系統已模擬買入 {pick['名稱']} 共 {shares} 股，進場價：{entry_p}")
        
        # 儲存結果
        report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
        status.update(label="✅ v23.3 全天候巡檢同步完成", state="complete")
    st.rerun()
