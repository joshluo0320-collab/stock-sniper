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
# 1. 系統初始化與報表管理
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
    df = pd.read_csv(REPORT_FILE, encoding='utf-8-sig')
    # 強制歷史錯誤數據小數點格式化
    if not df.empty:
        df["進場價"] = pd.to_numeric(df["進場價"], errors='coerce').round(1)
        df["當前撤退線"] = pd.to_numeric(df["當前撤退線"], errors='coerce').round(1)
    return df

@st.cache_data(ttl=86400)
def get_all_tw_stocks():
    try:
        url = "http://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = pd.read_html(url)[0]
        res.columns = res.iloc[0]
        res = res.iloc[1:]
        res = res[res['CFICode'] == 'ESVUTFR']
        
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
        return ["2317.TW", "2330.TW", "2352.TW", "3017.TW"], {"2317.TW":"鴻海", "2330.TW":"台積電", "2352.TW":"佳世達", "3017.TW":"奇鋐"}

def is_market_open():
    now = datetime.now()
    if now.weekday() > 4: return False
    current_time = now.hour * 100 + now.minute
    return 900 <= current_time <= 1330

# ============================================
# 2. 核心戰略解讀引擎 (嚴格格式化輸出)
# ============================================
def execute_sniper_v23_3(df, tid, name, trail_p, min_price, max_price):
    try:
        if df.empty or len(df) < 35: return None
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        
        df = df.dropna(subset=['Close', 'High', 'Low'])
        last_p = round(float(df['Close'].iloc[-1]), 1)
        
        # 價格區間過濾
        if not (min_price <= last_p <= max_price): return None
        
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma10 = df['Close'].rolling(10).mean().iloc[-1]
        
        # 1. 氣勢分析
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_slope = (ema12 - ema26).diff().iloc[-1]
        momentum_text = "🏎️ 全油門衝刺" if macd_slope > 0 else "🐢 動能減速"
        
        # 2. 路況分析
        bias_10 = round(((last_p / ma10) - 1) * 100, 1)
        if last_p > ma10 * 1.08:
            road_text = "🚨 嚴重超速(不追)"
        else:
            road_text = "🗺️ 前方無障礙" if last_p > ma5 else "⚠️ 路面顛簸"
            
        # 3. 能量分析
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = round((tr.rolling(14).mean().iloc[-1] / last_p) * 100, 1)
        energy_text = "⛽ 油量正常" if atr_ratio >= 1.5 else "🪫 缺乏波動"
        
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        if score < 0: score = 0
        if score > 100: score = 100
        
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 1)
        clean_code = tid.split(".")[0]

        return {
            "代號": clean_code, "股票名稱": name, "綜合勝率": f"{score}%", 
            "↑氣勢分析": momentum_text, "路況分析": road_text, "能量分析": energy_text, 
            "今日收盤": last_p, "明日建議進場區": f"{round(last_p*0.99, 1)} ~ {round(last_p*1.01, 1)}",
            "撤退線": withdrawal_line, "raw_score": score, "raw_ticker": tid
        }
    except: 
        return None

# ============================================
# 3. 多線程安全抓取單個個股數據 (防 Yahoo API 阻斷)
# ============================================
def fetch_and_evaluate(ticker, name, trail_pct, min_p, max_p):
    try:
        # 單股獨立下載防集體卡死，並縮短歷史範圍至 45 天加速掃描
        df = yf.Ticker(ticker).history(period="45d", progress=False)
        if df.empty: return None
        return execute_sniper_v23_3(df, ticker, name, trail_pct, min_p, max_p)
    except:
        return None

# ============================================
# 4. Streamlit 前端渲染
# ============================================
st.set_page_config(page_title="v23.3 策略實驗室", layout="wide")
st.title("🏹 v23.3 科學博弈系統 (全上市 1000+ 戰略版)")

report = get_report()
active_trades = report[report["狀態"] == "持有中"]

# 側邊欄
st.sidebar.header("🕹️ 戰略參數控制台")
target_win = st.sidebar.slider("🎯 買入勝率門檻 (%)", 50, 100, 60, step=5)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 10.0, 5.0, step=1.0)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 拒絕零股！股價區間設定")
st.sidebar.caption(f"單注預算: {PER_STOCK_BUDGET} 元")
min_p_input = st.sidebar.number_input("最低可容許股價 (元)", min_value=1.0, max_value=2000.0, value=50.0, step=5.0)
max_p_input = st.sidebar.number_input("最高可容許股價 (元)", min_value=1.0, max_value=2000.0, value=190.0, step=5.0)

if st.sidebar.button("🧹 重設庫存 (清空持股實驗)"):
    df = pd.DataFrame(columns=["狀態", "名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線", "出場日期", "出場價", "損益金額", "報酬率"])
    df.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("持股已完全清空，可重新進行獵殺測試")
    st.container().empty()
    st.rerun()

# 庫存看板顯示
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("🏃 當前系統持有部位")
    if not active_trades.empty:
        st.table(active_trades[["名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線"]])
    else:
        st.info("目前庫存無持股（等待雷達發動獵殺）。")

with col2:
    current_cash = TOTAL_BUDGET - (active_trades["進場價"] * active_trades["股數"]).sum()
    st.metric("💰 實證剩餘現金", f"{round(current_cash, 1)} 元")
    st.metric("⚖️ 市場狀態", "🟢 開盤中" if is_market_open() else "🔴 休市中 (全天候雷達運作)")

# ============================================
# 5. 地毯式獵殺同步引擎 (分批下載抗限制)
# ============================================
if st.button("🔴 啟動全台股 1,000+ 支標的之地毯式獵殺", type="primary"):
    with st.status("正在同步證交所地圖並執行深度掃描...", expanded=True) as status:
        
        tickers, names_map = get_all_tw_stocks()
        st.write(f"🌐 正在連線證交所抓取完整地圖... 鎖定 {len(tickers)} 支標的，啟動分批抗限制下載機制...")
        
        # 改用動態分批多線程，繞過大批量批量阻擋死穴
        radar_data = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_ticker = {
                executor.submit(fetch_and_evaluate, tk, names_map[tk], trail_pct, min_p_input, max_p_input): tk 
                for tk in tickers
            }
            for future in concurrent.futures.as_completed(future_to_ticker):
                res = future.result()
                if res is not None:
                    radar_data.append(res)
                    
        radar_df = pd.DataFrame(radar_data)
        
        if not radar_df.empty:
            passed_df = radar_df[
                (radar_df["raw_score"] >= target_win) & 
                (radar_df["路況分析"] == "🗺️ 前方無障礙") &
                (radar_df["能量分析"] == "⛽ 油量正常")
            ]
        else:
            passed_df = pd.DataFrame()
            
        status.update(label=f"🎯 獵殺完成！在 {len(radar_df)} 支成功獲取數據的結果中。", state="complete")
        
        # --- 渲染圖 2 綠色報告區 ---
        st.markdown("---")
        st.success(f"📊 報告：全市場共篩選出 {len(passed_df)} 支符合獵殺門檻標的。")
        
        if not passed_df.empty:
            display_df = passed_df.sort_values(by="raw_score", ascending=False).head(10)
            st.dataframe(display_df[["股票名稱", "代號", "綜合勝率", "↑氣勢分析", "路況分析", "能量分析", "今日收盤", "明日建議進場區"]], use_container_width=True, hide_index=True)
            
            # 【交易存檔同步】
            current_active_count = len(report[report["狀態"] == "持有中"])
            for _, pick in display_df.iterrows():
                if current_active_count >= MAX_POSITIONS: break
                if pick["raw_ticker"] in report[report["狀態"] == "持有中"]["代號"].values: continue
                
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
            st.info("💡 數據已成功全部下載。但在當前的「勝率門檻」與「股價區間」限制下，今日暫無個股滿足主升段條件。建議調寬左側參數再試一次。")
