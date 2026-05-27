import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import urllib3
import os
from datetime import datetime
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
@st.cache_data(ttl=86400)  # 一天只爬一次，加速 UI 反應
def get_all_tw_stocks():
    try:
        url = "http://isin.twse.com.tw/isin/C_public.jsp?strMode=2" # 證交所上市證券組群頁
        res = pd.read_html(url)[0]
        res.columns = res.iloc[0]
        res = res.iloc[1:]
        
        # 篩選出純股票 (排除 ETF、權證、存託憑證)
        res = res[res['CFICode'] == 'ESVUTFR'] 
        
        tickers = []
        names_map = {}
        for item in res['有價證券代號及名稱']:
            try:
                parts = item.split('\u3000') # 依據全形空白拆分代號與名稱
                if len(parts) == 2 and len(parts[0]) == 4: # 確保是四碼台股
                    ticker_tw = f"{parts[0]}.TW"
                    tickers.append(ticker_tw)
                    names_map[ticker_tw] = parts[1]
            except:
                continue
        return tickers, names_map
    except Exception as e:
        # 備用機制：若證交所阻擋，維持基礎權值標的防呆
        st.error(f"證交所名單爬取失敗: {e}，啟用備用權值名單。")
        return ["2317.TW", "2330.TW", "2352.TW", "0050.TW"], {"2317.TW":"鴻海", "2330.TW":"台積電", "2352.TW":"佳世達", "0050.TW":"元大台灣50"}

def is_market_open():
    now = datetime.now()
    if now.weekday() > 4: return False
    current_time = now.hour * 100 + now.minute
    return 900 <= current_time <= 1330

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
# ⚡ 高效能多執行緒多股掃描引擎
# ============================================
def scan_market_parallel(tickers, names_map, trail_pct):
    radar_results = []
    # 使用 yfinance 批量下載所有股票歷史數據 (速度比單檔下載快 50 倍)
    with st.spinner(f"正在從 Yahoo Finance 批量同步全台灣 {len(tickers)} 檔上市股票數據..."):
        all_data = yf.download(tickers, period="60d", group_by='ticker', progress=False)
    
    # 使用多核心平行計算各股指標
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {}
        for ticker in tickers:
            try:
                # 提取單檔股票的 DataFrame
                if len(tickers) == 1:
                    df = all_data
                else:
                    df = all_data[ticker]
                if df.empty or df['Close'].isnull().all(): continue
                future = executor.submit(execute_sniper_v23_3, df, ticker, names_map[ticker], trail_pct)
                future_to_
