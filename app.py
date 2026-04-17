import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import os
from datetime import datetime
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統常數 (v23.3 獵殺進化版)
# ============================================
REPORT_FILE = "v23_sim_report.csv"
TOTAL_BUDGET = 190000
MAX_POSITIONS = 3
PER_STOCK_BUDGET = 60000
FRICTION_COST = 0.005  # 0.5% 摩擦成本

# ============================================
# 2. 核心邏輯函式
# ============================================
def get_report():
    if not os.path.exists(REPORT_FILE):
        df = pd.DataFrame(columns=["狀態", "名稱", "代號", "進場日期", "進場價", "股數", "最高價", "當前撤退線", "出場日期", "出場價", "損益金額", "報酬率"])
        df.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    return pd.read_csv(REPORT_FILE, encoding='utf-8-sig')

def is_market_open():
    now = datetime.now()
    if now.weekday() > 4: return False
    curr_time = now.hour * 100 + now.minute
    return 900 <= curr_time <= 1330

def execute_sniper_v23_logic(df, tid, name, trail_p):
    """
    單一標的邏輯運算：包含活性濾網與動能評分
    """
    try:
        if df.empty or len(df) < 40: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        
        last_p = round(float(df['Close'].iloc[-1]), 1)
        # 1. 乖離過濾 (禁止追高)
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        if last_p > ma5 * 1.05: return None 
        
        # 2. 活性濾網 (量能需大於5日均量1.5倍)
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        if df['Volume'].iloc[-1] < vol_ma5 * 1.5: return None
        
        # 3. ATR 波動力
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = (tr.rolling(14).mean().iloc[-1] / last_p) * 100
        if atr_ratio < 1.5: return None

        # 4. 動能評分 (MACD Slope + 20D Breakout)
        macd = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
        macd_slope = macd.diff().iloc[-1]
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        
        # 5. 初步撤退線 (進場用)
        init_withdrawal = round(last_p * (1 - trail_p/100), 1)

        return {"代號": tid, "名稱": name, "勝率": score, "現價": last_p, "撤退線": init_withdrawal}
    except: return None

@st.cache_data(ttl=86400)
def get_market_map():
    tickers, names_map = [], {}
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=10)
            res.encoding = 'big5'; soup = BeautifulSoup(res.text, 'lxml')
            for row in soup.find_all('tr'):
                tds = row.find_all('td')
                if len(tds) > 0:
                    raw = tds[0].text.strip().split()
                    if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                        suffix = ".TW" if "strMode=2" in url else ".TWO"
                        tickers.append(f"{raw[0]}{suffix}"); names_map[raw[0]] = raw[1]
        except: continue
    return tickers, names_map

# ============================================
# 3. 介面與巡檢邏輯
# ============================================
st.set_page_config(page_title="v23.3 獵殺實驗室", layout="wide")
st.title("🏹 v23.3 趨勢奔跑實證系統")

# --- 側邊欄維護區 ---
st.sidebar.header("🛠️ 參數設定")
target_win = st.sidebar.slider("🎯 買入勝率門檻", 60, 95, 75, step=5)
trail_pct = st.sidebar.slider("🛡️ 追蹤回落停利 (%)", 1.0, 10.0, 3.0, step=0.5)

if st.sidebar.button("🚨 重置報表"):
    empty_df = pd.DataFrame(columns=["狀態", "名稱", "代號", "進場日期", "進場價", "股數", "最高價", "當前撤退線", "出場日期", "出場價", "損益金額", "報酬率"])
    empty_df.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    st.rerun()

# 數據讀取
report = get_report()
active_trades = report[report["狀態"] == "持有中"]
used_cash = (active_trades["進場價"] * active_trades["股數"]).sum()

# 儀表板
m1, m2, m3 = st.columns(3)
m1.metric("💰 剩餘現金", f"{int(TOTAL_BUDGET - used_cash)} 元")
m2.metric("📦 持有部位", f"{len(active_trades)} / {MAX_POSITIONS}")
m3.metric("⚖️ 市場狀態", "🟢 開盤中" if is_market_open() else "🔴 休市中")

# 顯示庫存
st.subheader("🏃 目前持有部位 (追蹤止盈模式)")
if not active_trades.empty:
    st.table(active_trades[["名稱", "代號", "進場價", "最高價", "當前撤退線", "報酬率"]])
else:
    st.info("目前無持股，等待動能標的出現。")

# 執行巡檢
if st.button("🔴 執行全自動巡檢 (加速版)", type="primary"):
    with st.status("系統巡檢中...", expanded=True) as status:
        # A. 處理賣出與撤退線更新
        if not active_trades.empty:
            for idx, row in active_trades.iterrows():
                symbol = f"{row['代號']}.TW" if len(str(row['代號'])) == 4 else f"{row['代號']}.TWO"
                data = yf.download(symbol, period="5d", progress=False)
                if not data.empty:
                    curr_p = round(float(data['Close'].iloc[-1]), 1)
                    # 更新最高價與撤退線
                    new_high = max(row['最高價'], curr_p)
                    # 獲利 > 5% 啟動保本：撤退線不低於進場成本
                    profit_pct = (curr_p - row['進場價']) / row['進場價'] * 100
                    base_stop = new_high * (1 - trail_pct/100)
                    if profit_pct > 5.0:
                        new_stop = max(base_stop, row['進場價'] * 1.005) # 保本 + 手續費
                    else:
                        new_stop = base_stop
                    
                    report.at[idx, "最高價"] = new_high
                    report.at[idx, "當前撤退線"] = round(new_stop, 1)
                    report.at[idx, "報酬率"] = f"{round(profit_pct, 2)}%"

                    if curr_p < row['當前撤退線']:
                        exit_price = round(curr_p * (1 - FRICTION_COST), 1)
                        report.at[idx, "狀態"], report.at[idx, "出場價"] = "已結案", exit_price
                        report.at[idx, "出場日期"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        report.at[idx, "損益金額"] = int((exit_price - row['進場價']) * row['股數'])
                        st.warning(f"⚠️ {row['名稱']} 觸及撤退線，執行鎖利出場。")

        # B. 處理買入 (限開盤且有空位)
        if is_market_open() and len(report[report["狀態"] == "持有中"]) < MAX_POSITIONS:
            st.write("正在掃描全市場潛在動能標的...")
            tickers, names_map = get_market_map()
            
            # 隨機抽樣或選取前 N 名進行掃描以示範，實務可放開
            target_tickers = tickers[:300] # 先掃描前 300 支確保速度
            
            def scan_task(tid):
                name = names_map.get(tid[:4], "未知")
                df = yf.download(tid, period="60d", progress=False)
                return execute_sniper_v23_logic(df, tid[:4], name, trail_pct)

            all_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(scan_task, t) for t in target_tickers]
                for f in concurrent.futures.as_completed(futures):
                    res = f.result()
                    if res and res['勝率'] >= target_win:
                        # 檢查是否已在持股中
                        if str(res['代號']) not in report[report["狀態"]=="持有中"]['代號'].astype(str).values:
                            all_results.append(res)
            
            # 按勝率排序
            all_results.sort(key=lambda x: x['勝率'], reverse=True)
            
            # 執行買入
            slots = MAX_POSITIONS - len(report[report["狀態"] == "持有中"])
            for i in range(min(slots, len(all_results))):
                target = all_results[i]
                shares = int(PER_STOCK_BUDGET / target['現價'])
                new_row = {
                    "狀態": "持有中", "名稱": target['名稱'], "代號": target['代號'],
                    "進場日期": datetime.now().strftime("%Y-%m-%d"),
                    "進場價": target['現價'], "股數": shares,
                    "最高價": target['現價'], "當前撤退線": target['撤退線'],
                    "報酬率": "0%"
                }
                report = pd.concat([report, pd.DataFrame([new_row])], ignore_index=True)
                st.success(f"🏹 獵殺成功：{target['名稱']} ({target['代號']}) 進場。")

        report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
        status.update(label="✅ 巡檢同步完成", state="complete")
    st.rerun()
