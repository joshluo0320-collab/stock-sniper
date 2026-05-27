import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import urllib3
import os
from datetime import datetime
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統初始化與報表設定
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

# 動態全台股上市股票抓取
@st.cache_data(ttl=86400)
def get_all_tw_stocks():
    try:
        url = "http://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = pd.read_html(url)[0]
        res.columns = res.iloc[0]
        res = res.iloc[1:]
        res = res[res['CFICode'] == 'ESVUTFR'] # 純上市普通股
        
        tickers = []
        names_map = {}
        for item in res['有價證券代號及名稱']:
            try:
                parts = item.split('\u3000')
                if len(parts) == 2 and len(parts[0]) == 4:
                    ticker_tw = f"{parts[0]}.TW"
                    tickers.append(ticker_tw)
                    names_map[ticker_tw] = parts[1]
            except:
                continue
        return tickers, names_map
    except:
        # 核心防呆備用名單
        return ["2317.TW", "2330.TW", "2352.TW", "3017.TW"], {"2317.TW":"鴻海", "2330.TW":"台積電", "2352.TW":"佳世達", "3017.TW":"奇鋐"}

def is_market_open():
    now = datetime.now()
    if now.weekday() > 4: return False
    current_time = now.hour * 100 + now.minute
    return 900 <= current_time <= 1330

# ============================================
# 2. 核心戰略解讀引擎 (復刻圖 2 核心邏輯)
# ============================================
def execute_sniper_v23_3(df, tid, name, trail_p, min_price, max_price):
    try:
        if df.empty or len(df) < 40: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        last_p = round(float(df['Close'].iloc[-1]), 1)
        
        # 價格區間過濾 (解鎖拒絕零股功能)
        if not (min_price <= last_p <= max_price): return None
        
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma10 = df['Close'].rolling(10).mean().iloc[-1]
        
        # 1. 氣勢分析 (MACD 斜率)
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_slope = (ema12 - ema26).diff().iloc[-1]
        momentum_text = "🏎️ 全油門衝刺" if macd_slope > 0 else "🐢 動能減速"
        
        # 2. 路況分析 (10MA 乖離防禦機制)
        bias_10 = round(((last_p / ma10) - 1) * 100, 1)
        if last_p > ma10 * 1.08:
            road_text = "🚨 嚴重超速(不追)"
        else:
            road_text = "🗺️ 前方無障礙" if last_p > ma5 else "⚠️ 路面顛簸"
            
        # 3. 能量分析 (ATR 波動度)
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = round((tr.rolling(14).mean().iloc[-1] / last_p) * 100, 1)
        energy_text = "⛽ 油量正常" if atr_ratio >= 1.5 else "🪫 缺乏波動"
        
        # 20日突破加分項
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        
        # 綜合勝率計算
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        if score < 0: score = 0
        if score > 100: score = 100
        
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 1)

        return {
            "代號": parts_code := tid.split(".")[0], 
            "股票名稱": name, 
            "綜合勝率": f"{score}%", 
            "↑氣勢分析": momentum_text, 
            "路況分析": road_text, 
            "能量分析": energy_text, 
            "今日收盤": last_p, 
            "明日建議進場區": f"{round(last_p*0.99, 1)} ~ {round(last_p*1.01, 1)}",
            "撤退線": withdrawal_line,
            "raw_score": score,
            "raw_ticker": tid
        }
    except: 
        return None

# ============================================
# 3. Streamlit 前端視覺渲染
# ============================================
st.set_page_config(page_title="v23.3 策略實驗室", layout="wide")
st.title("🏹 v23.3 科學博弈系統 (全上市 1000+ 戰略版)")

report = get_report()
active_trades = report[report["狀態"] == "持有中"]

# --- 側邊欄控制台 (優化功能) ---
st.sidebar.header("🕹️ 戰略參數控制台")
target_win = st.sidebar.slider("🎯 買入勝率門檻 (%)", 50, 100, 80, step=5)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 10.0, 5.0, step=1.0)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 拒絕零股！股價區間設定")
st.sidebar.caption(f"單注預算: {PER_STOCK_BUDGET} 元")
min_p_input = st.sidebar.number_input("最低可容許股價 (元)", min_value=1.0, max_value=2000.0, value=10.0, step=5.0)
max_p_input = st.sidebar.number_input("最高可容許股價 (元)", min_value=1.0, max_value=2000.0, value=60.0, step=5.0)
st.sidebar.info(f"💡 目前設定僅會掃描可購買約 {int(PER_STOCK_BUDGET/max_p_input)} ~ {int(PER_STOCK_BUDGET/min_p_input)} 股之標的，鎖定整張交易。")

if st.sidebar.button("🧹 重設庫存 (清空持股實驗)"):
    df = pd.DataFrame(columns=["狀態", "名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線", "出場日期", "出場價", "損益金額", "報酬率"])
    df.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("持股已完全清空，可重新進行獵殺測試")
    st.rerun()

# 庫存看板顯示
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("🏃 當前系統持有部位")
    if not active_trades.empty:
        # 強制小數點後第一位
        disp_active = active_trades.copy()
        disp_active["進場價"] = disp_active["進場價"].round(1)
        disp_active["當前撤退線"] = disp_active["當前撤退線"].round(1)
        st.table(disp_active[["名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線"]])
    else:
        st.info("目前庫存無持股（等待雷達發動獵殺）。")

with col2:
    current_cash = TOTAL_BUDGET - (active_trades["進場價"] * active_trades["股數"]).sum()
    st.metric("💰 實證剩餘現金", f"{round(current_cash, 1)} 元")
    st.metric("⚖️ 市場狀態", "🟢 開盤中" if is_market_open() else "🔴 休市中 (全天候雷達運作)")

# ============================================
# 4. 戰術巡檢核心與圖 2 視覺生成
# ============================================
if st.button("🔴 啟動全台股 1,000+ 支標的之地毯式獵殺", type="primary"):
    with st.status("正在同步證交所地圖並執行深度掃描...", expanded=True) as status:
        
        tickers, names_map = get_all_tw_stocks()
        st.write(f"🌐 正在連線證交所抓取完整地圖... 鎖定 {len(tickers)} 支標的，開始量價深度掃描...")
        
        # 批量同步下載
        all_data = yf.download(tickers, period="40d", group_by='ticker', progress=False)
        
        radar_data = []
        for ticker in tickers:
            try:
                if len(tickers) == 1: df = all_data
                else: df = all_data[ticker]
                if df.empty or df['Close'].isnull().all(): continue
                
                res = execute_sniper_v23_3(df, ticker, names_map[ticker], trail_pct, min_p_input, max_p_input)
                if res: radar_data.append(res)
            except:
                continue
        
        radar_df = pd.DataFrame(radar_data)
        
        # 篩選出符合門檻且通過安全路況的黃金候選股
        if not radar_df.empty:
            passed_df = radar_df[
                (radar_df["raw_score"] >= target_win) & 
                (radar_df["路況分析"] == "🗺️ 前方無障礙") &
                (radar_df["能量分析"] == "⛽ 油量正常")
            ]
        else:
            passed_df = pd.DataFrame()
            
        status.update(label=f"🎯 獵殺完成！在 {len(radar_df)} 支篩選結果中。", state="complete")
        
        # --- 完美還原圖 2 綠色動態報告區 ---
        st.markdown("---")
        st.success(f"📊 報告：全市場共篩選出 {len(passed_df)} 支符合獵殺門檻標的。")
        
        if not passed_df.empty:
            # 格式化輸出
            display_df = passed_df.sort_values(by="raw_score", ascending=False).head(10)
            st.dataframe(display_df[["股票名稱", "代號", "綜合勝率", "↑氣勢分析", "路況分析", "能量分析", "今日收盤", "明日建議進場區"]], use_container_width=True, hide_index=True)
            
            # 【自動化模擬進場交易同步】
            current_active_count = len(report[report["狀態"] == "持有中"])
            for _, pick in display_df.iterrows():
                if current_active_count >= MAX_POSITIONS: break
                if pick["raw_ticker"] in report[report["狀態"] == "持有中"]["代號"].values: continue
                
                # 計算可以買進的整股張數/股數
                shares = int(PER_STOCK_BUDGET / (pick["今日收盤"] * (1 + FRICTION_COST)))
                if shares > 0:
                    entry_p = round(pick["今日收盤"] * (1 + FRICTION_COST), 1)
                    new_trade = pd.DataFrame([{
                        "狀態": "持有中", "名稱": pick["股票名稱"], "代號": pick["raw_ticker"],
                        "進場日期": datetime.now().strftime("%Y-%m-%d %H:%M") + (" (盤後)" if not is_market_open() else ""),
                        "進場價": entry_p, "股數": shares, "當前撤退線": pick["撤退線"],
                        "出場日期": np.nan, "出場價": np.nan, "損益金額": 0, "報酬率": "0.0%"
                    }])
                    report = pd.concat([report, new_trade], ignore_index=True)
                    current_active_count += 1
                    st.toast(f"🏹 觸發模擬交易：買入 {pick['股票名稱']} {shares} 股")
            
            report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
        else:
            st.info("💡 雖然掃描了全上市個股，但在目前的「勝率門檻」與「股價區間」限制下，今日暫無個股觸發主升段條件。建議調寬左側參數再試一次。")
