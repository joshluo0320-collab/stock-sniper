import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import os
from datetime import datetime

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 系統參數 (19 萬科學博弈設定)
# ============================================
TOTAL_BUDGET = 190000
MAX_POSITIONS = 3
PER_STOCK_BUDGET = 60000
FRICTION_COST = 0.005  # 手續費 + 稅 + 滑價 (合計 0.5%)
REPORT_FILE = "v23_sim_report.csv"

# 初始化/獲取報表
def get_report():
    if not os.path.exists(REPORT_FILE):
        df = pd.DataFrame(columns=[
            "狀態", "名稱", "代號", "進場日期", "進場價", "股數", 
            "當前撤退線", "出場日期", "出場價", "損益金額", "報酬率"
        ])
        df.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
    return pd.read_csv(REPORT_FILE, encoding='utf-8-sig')

# ============================================
# 2. 核心獵殺邏輯 (v23.2 佛系優化版)
# ============================================
def execute_sniper_v23(df, tid, name, trail_p):
    try:
        if df.empty or len(df) < 40: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])

        last_p = round(float(df['Close'].iloc[-1]), 1)
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        
        # [佛系過濾]：乖離過大不追 (避免 10:00 買在最高點)
        if last_p > ma5 * 1.05: return None 

        # [ATR 波動力]：踢除心跳停止的牛皮股
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = (tr.rolling(14).mean().iloc[-1] / last_p) * 100
        if atr_ratio < 1.5: return None

        # [動能指標]
        macd_slope = (df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()).diff().iloc[-1]
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        
        # [綜合勝率]
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 1)

        return {"代號": tid, "名稱": name, "勝率": score, "現價": last_p, "撤退線": withdrawal_line, "ATR": atr_ratio}
    except: return None

# ============================================
# 3. 名單抓取工具
# ============================================
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
# 4. Streamlit UI 戰略中樞
# ============================================
st.set_page_config(page_title="v23.2 模擬實證實驗室", layout="wide")
st.title("🏹 v23.2 科學博弈實證系統 (19萬沙盒)")

# 側邊欄控制
st.sidebar.header("🕹️ 實驗參數設定")
target_win = st.sidebar.slider("🎯 買入勝率門檻", 60, 95, 80, step=5)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 10.0, 5.0, step=1.0)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 10000, 500, step=500)

# --- A. 模擬報表區 ---
report = get_report()
active_trades = report[report["狀態"] == "持有中"]
closed_trades = report[report["狀態"] == "已結案"]

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("🏃 當前持有部位")
    if not active_trades.empty:
        st.table(active_trades[["名稱", "代號", "進場日期", "進場價", "股數", "當前撤退線"]])
    else:
        st.info("目前無持有部位，請於 10:00 執行巡檢。")

with col2:
    current_cash = TOTAL_BUDGET - (active_trades["進場價"] * active_trades["股數"]).sum()
    st.metric("💰 剩餘可用現金", f"{int(current_cash)} 元")
    st.metric("📦 當前持股數", f"{len(active_trades)} / {MAX_POSITIONS}")

# --- B. 一鍵執行同步 (最核心按鈕) ---
if st.button("🔴 執行定時巡檢 (選股 + 買賣同步)", type="primary"):
    with st.status("正在同步報表與掃描市場...", expanded=True) as status:
        # 1. 檢查賣出 (審判)
        if not active_trades.empty:
            st.write("🔍 正在檢查庫存是否觸發撤退...")
            for idx, row in active_trades.iterrows():
                suffix = ".TW" if len(str(row['代號'])) == 4 else "" # 簡化處理
                data = yf.download(f"{row['代號']}{suffix}", period="5d", progress=False)
                if data.empty: data = yf.download(f"{row['代號']}.TWO", period="5d", progress=False)
                
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
                        st.warning(f"⚠️ {row['名稱']} 觸發撤退！結算損益: {int(p_l)} 元")

        # 2. 掃描新獵物 (買入)
        if len(report[report["狀態"] == "持有中"]) < MAX_POSITIONS:
            st.write("📡 掃描全台股符合 v23.2 之獵物...")
            tickers, names_map = get_market_map()
            final_picks = []
            chunk_size = 60
            for i in range(0, len(tickers), chunk_size):
                chunk = tickers[i : i + chunk_size]
                try:
                    data_chunk = yf.download(chunk, period="6mo", group_by='ticker', progress=False)
                    for t in chunk:
                        tid = t.split(".")[0]
                        df_s = data_chunk[t] if len(chunk) > 1 else data_chunk
                        res = execute_sniper_v23(df_s, tid, names_map.get(tid, tid), trail_pct)
                        if res and res['勝率'] >= target_win:
                            # 檢查成交量門檻
                            if (df_s['Volume'].tail(5).mean() / 1000) >= vol_limit:
                                final_picks.append(res)
                except: continue
            
            # 排序並嘗試買入
            final_picks = sorted(final_picks, key=lambda x: x['勝率'], reverse=True)
            for pick in final_picks:
                if len(report[report["狀態"] == "持有中"]) < MAX_POSITIONS:
                    # 買入計算
                    buy_price = round(pick['現價'] * (1 + FRICTION_COST), 1)
                    qty = int(PER_STOCK_BUDGET / (buy_price * 1000)) * 1000
                    if qty >= 1000:
                        new_row = {
                            "狀態": "持有中", "名稱": pick['名稱'], "代號": pick['代號'],
                            "進場日期": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "進場價": buy_price, "股數": qty, "當前撤退線": pick['撤退線'],
                            "出場日期": "-", "出場價": 0, "損益金額": 0, "報酬率": "-"
                        }
                        report = pd.concat([report, pd.DataFrame([new_row])], ignore_index=True)
                        st.success(f"🚀 模擬進場: {pick['名稱']} ({qty}股) @ {buy_price}")
        
        report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')
        status.update(label="✅ 巡檢與報表同步完成", state="complete")
    st.rerun()

# --- C. 歷史紀錄區 ---
if not closed_trades.empty:
    st.divider()
    st.subheader("📈 已結案歷史戰績")
    st.table(closed_trades)
    net_profit = closed_trades["損益金額"].sum()
    st.write(f"📊 累計實驗淨損益： **{int(net_profit)} 元**")

st.info("💡 **佛系操作指南**：請於每日 **10:00** 與 **13:15** 點擊上方紅鈕。系統會自動根據最新股價與 v23.2 邏輯處理帳本。")
