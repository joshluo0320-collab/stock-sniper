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
# 🎯 動態爬取台灣股市所有「上市」股票名單 (1000+)
# ============================================
@st.cache_data(ttl=86400)  # 一天僅爬取一次，保障啟動效能
def get_all_tw_stocks():
    try:
        url = "http://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = pd.read_html(url)[0]
        res.columns = res.iloc[0]
        res = res.iloc[1:]
        
        # 嚴格篩選純股票 (CFICode == 'ESVUTFR' 代表上市普通股，排除商品與權證)
        res = res[res['CFICode'] == 'ESVUTFR'] 
        
        tickers = []
        names_map = {}
        for item in res['有價證券代號及名稱']:
            try:
                parts = item.split('\u3000')  # 依全形空白拆分
                if len(parts) == 2 and len(parts[0]) == 4:  # 鎖定四碼常態股票
                    ticker_tw = f"{parts[0]}.TW"
                    tickers.append(ticker_tw)
                    names_map[ticker_tw] = parts[1]
            except:
                continue
        return tickers, names_map
    except Exception as e:
        st.error(f"⚠️ 證交所即時名單爬取失敗: {e}，啟用核心權值實證名單防呆。")
        return ["2317.TW", "2330.TW", "2352.TW", "0052.TW"], {"2317.TW":"鴻海", "2330.TW":"台積電", "2352.TW":"佳世達", "0052.TW":"富邦科技"}

def is_market_open():
    now = datetime.now()
    if now.weekday() > 4: return False
    current_time = now.hour * 100 + now.minute
    return 900 <= current_time <= 1330

# ============================================
# 3. 核心獵殺邏輯核心 (v23.3 10MA優化版)
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
        
        bias_10 = round(((last_p / ma10) - 1) * 100, 2)
        
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = round((tr.rolling(14).mean().iloc[-1] / last_p) * 100, 2)

        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_slope = (ema12 - ema26).diff().iloc[-1]
        
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        
        # 科學計分公式
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 1)

        passed_filter = "通過"
        if last_p > ma10 * 1.08: passed_filter = "阻斷 (10MA過高)"
        if atr_ratio < 1.5: passed_filter = "阻斷 (ATR不足)"

        return {
            "代號": tid, "名稱": name, "勝率分數": score, "現價": last_p, 
            "撤退線": withdrawal_line, "ATR": atr_ratio, "10MA乖離%": bias_10, "濾網狀態": passed_filter
        }
    except: 
        return None

# ============================================
# 4. Streamlit UI 佈局
# ============================================
st.set_page_config(page_title="v23.3 全市場實證實驗室", layout="wide")
st.title("🏹 v23.3 科學博弈系統 (全上市 1000+ 戰略版)")

report = get_report()
active_trades = report[report["狀態"] == "持有中"]

# --- 側邊欄：要求 1 重新鎖定 50 - 100 區間 ---
st.sidebar.header("🕹️ 戰略參數控制台")
target_win = st.sidebar.slider("🎯 買入勝率門檻", 50, 100, 60, step=5)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 10.0, 5.0, step=1.0)

if st.sidebar.button("🧹 清除異常重複持股"):
    report = report.drop_duplicates(subset=['代號', '狀態'], keep='first')
    report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("重複項已清理")
    st.rerun()

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("🏃 當前系統持有部位")
    if not active_trades.empty:
        st.table(active_trades[["名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線"]])
    else:
        st.info("目前庫存無持股（等待雷達發動獵殺）。")

with col2:
    current_cash = TOTAL_BUDGET - (active_trades["進場價"] * active_trades["股數"]).sum()
    st.metric("💰 實證剩餘現金", f"{int(current_cash)} 元")
    st.metric("⚖️ 市場狀態", "🟢 開盤中" if is_market_open() else "🔴 休市中 (全天候雷達運作)")

# ============================================
# 5. 執行全市場平行掃描與巡檢
# ============================================
if st.button("🔴 啟動全市場地毯式巡檢 (1000+上市標的同步)", type="primary"):
    with st.status("正在下載全市場歷史數據並執行平行計算...", expanded=True) as status:
        
        # 取得證交所最新完整上市名單
        tickers, names_map = get_all_tw_stocks()
        st.write(f"已成功載入 {len(tickers)} 檔台灣上市普通股名單，開始多執行緒異步掃描...")
        
        # 【步驟一】利用多執行緒平行抓取與試算指標
        radar_data = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            future_to_ticker = {
                executor.submit(execute_sniper_v23_3, yf.download(tk, period="40d", progress=False), tk, names_map[tk], trail_pct): tk 
                for tk in tickers
            }
            for future in concurrent.futures.as_completed(future_to_ticker):
                res = future.result()
                if res:
                    radar_data.append(res)
        
        radar_df = pd.DataFrame(radar_data)
        
        # 【步驟二】即時渲染篩選看板（只顯示通過濾網且得分高於門檻的「黃金名單」）
        st.write("### 📡 雷達即時偵測：符合主升段擴張標的")
        passed_df = radar_df[(radar_df["勝率分數"] >= target_win) & (radar_df["濾網狀態"] == "通過")]
        
        if not passed_df.empty:
            st.dataframe(passed_df[["名稱", "代號", "現價", "勝率分數", "10MA乖離%", "ATR"]], use_container_width=True)
        else:
            st.info("目前全市場 1000+ 標的中，無任何股票同時突破勝率門檻且未爆乖離。")

        # 【步驟三】執行自動買賣報表同步
        # 1. 審判：庫存停損檢驗
        if not active_trades.empty:
            for idx, row in active_trades.iterrows():
                stock_data = yf.download(row['代號'], period="5d", progress=False)
                if not stock_data.empty:
                    if isinstance(stock_data.columns, pd.MultiIndex): stock_data.columns = stock_data.columns.get_level_values(0)
                    curr_p = round(float(stock_data['Close'].iloc[-1]), 1)
                    if curr_p < row['當前撤退線']:
                        exit_price = round(curr_p * (1 - FRICTION_COST), 1)
                        p_l = (exit_price - row['進場價']) * row['股數']
                        report.at[idx, "狀態"] = "已結案"
                        report.at[idx, "出場日期"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        report.at[idx, "出場價"] = exit_price
                        report.at[idx, "損益金額"] = int(p_l)
                        report.at[idx, "報酬率"] = f"{round((exit_price/row['進場價']-1)*100, 2)}%"
                        st.warning(f"⚠️ 庫存 {row['名稱']} 已跌破撤退線，觸發審判點強制出場！")

        # 2. 獵殺：符合條件者自動模擬寫入庫存
        current_active_count = len(report[report["狀態"] == "持有中"])
        if current_active_count < MAX_POSITIONS and not passed_df.empty:
            # 依據分數高低排序，優先獵殺高分標的
            passed_df = passed_df.sort_values(by="勝率分數", ascending=False)
            
            for _, pick in passed_df.iterrows():
                if pick["代號"] in report[report["狀態"] == "持有中"]["代號"].values:
                    continue
                if current_active_count >= MAX_POSITIONS:
                    break
                
                shares = int(PER_STOCK_BUDGET / (pick["現價"] * (1 + FRICTION_COST)))
                if shares > 0:
                    entry_p = round(pick["現價"] * (1 + FRICTION_COST), 1)
                    new_trade = pd.DataFrame([{
                        "狀態": "持有中", "名稱": pick["名稱"], "代號": pick["代號"],
                        "進場日期": datetime.now().strftime("%Y-%m-%d %H:%M") + (" (盤後測試)" if not is_market_open() else ""),
                        "進場價": entry_p, "股數": shares, "當前撤退線": pick["撤退線"],
                        "出場日期": np.nan, "出場價": np.nan, "損益金額": 0, "報酬率": "0.0%"
                    }])
                    report = pd.concat([report, new_trade], ignore_index=True)
                    current_active_count += 1
                    st.success(f"🏹 獵殺成功！v23.3 系統已自動將高分標的 {pick['名稱']} ({pick['代號']}) 寫入實證持股。")
        
        report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
        status.update(label="✅ 全市場 1000+ 標的掃描與巡檢同步完成", state="complete")
    st.rerun()
