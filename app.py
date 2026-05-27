import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 核心獵殺邏輯 (v23.3 主升段優化版)
# ============================================
def execute_sniper_v23(df, tid, name, vol_gate, trail_p, min_price, max_price):
    try:
        if df.empty or len(df) < 40: return None
        
        # 處理 yfinance 多重索引問題並清洗無效數據
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])

        # 基礎現價 (嚴格取到小數點第一位)
        last_p = round(float(df['Close'].iloc[-1]), 1) 
        
        # --- [優化 2：解鎖股價範圍過濾，拒絕零股] ---
        if not (min_price <= last_p <= max_price): return None

        # --- [ATR 波動力分析] ---
        tr = pd.concat([
            df['High'] - df['Low'], 
            abs(df['High'] - df['Close'].shift(1)), 
            abs(df['Low'] - df['Close'].shift(1))
        ], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean().iloc[-1]
        volatility_ratio = (atr_14 / last_p) * 100
        
        # 指標計算：10MA 與 MACD 斜率
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        
        # --- [優化 1：方案 B 核心修正，導入 10MA 戰略緩衝線] ---
        ma10 = df['Close'].rolling(10).mean().iloc[-1]
        
        ema_12 = df['Close'].ewm(span=12).mean()
        ema_26 = df['Close'].ewm(span=26).mean()
        macd_slope = (ema_12 - ema_26).diff().iloc[-1]
        
        # 20日高點突破判斷
        high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
        is_break = last_p > high_20
        
        # 量比計算
        avg_v_5 = df['Volume'].tail(5).mean() / 1000
        v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5 if avg_v_5 > 0 else 0

        # --- [優化 1 延續：計分權重改依循更具緩衝力的 10MA 基準] ---
        win_score = int(((50 if last_p > ma10 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        if win_score < 0: win_score = 0
        if win_score > 100: win_score = 100
        
        # 動態撤退線 (嚴格取到小數點第一位)
        dynamic_trail = min(max(trail_p, 3.5), 7.0) 
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - dynamic_trail/100)), 1)

        # 隔日沖風險辨識 (量比過高且漲幅大)
        today_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) * 100
        risk_label = "⚠️ 隔日沖" if (v_ratio > 2.8 and today_ret > 6) else "✅ 穩健"

        return {
            "名稱": name, "代號": tid, "勝率": win_score,
            "現價": last_p, "撤退線": withdrawal_line, 
            "波動力(ATR)": f"{round(volatility_ratio, 2)}%",
            "油門": "🏎️ 加速" if macd_slope > 0 else "🐢 減速",
            "能量": "⛽ 爆量" if v_ratio > 1.5 else "🚗 正常",
            "路況": "🛣️ 無壓" if is_break else "🚧 有牆",
            "建議進場區": f"{round(last_p * 0.98, 1)}~{round(last_p * 0.995, 1)}",
            "風險": risk_label,
            "ATR_VAL": volatility_ratio # 隱藏過濾指標
        }
    except: return None

# ============================================
# 2. 名單抓取工具 (過濾普通股)
# ============================================
@st.cache_data(ttl=86400)
def get_market_map():
    tickers, names_map = [], {}
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=10)
            res.encoding = 'big5'
            soup = BeautifulSoup(res.text, 'lxml')
            for row in soup.find_all('tr'):
                tds = row.find_all('td')
                if len(tds) > 0:
                    raw = tds[0].text.strip().split()
                    # 確保過濾掉無效權證，專注純上市櫃股票
                    if len(tds) > 4 and tds[4].text.strip() != 'ESVUTFR': continue
                    if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                        suffix = ".TW" if "strMode=2" in url else ".TWO"
                        tickers.append(f"{raw[0]}{suffix}")
                        names_map[raw[0]] = raw[1]
        except: continue
    return tickers, names_map

# ============================================
# 3. Streamlit UI 戰略介面 (PM 規格)
# ============================================
st.set_page_config(page_title="獵殺系統 v23.3", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台 v23.3")
target_win = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 15.0, 5.0, step=1.0)

# --- [優化 2：新增股價範圍控制台，取代舊版單張預算上限] ---
st.sidebar.markdown("---")
st.sidebar.subheader("💰 拒絕零股！股價自選區間")
min_price_input = st.sidebar.number_input("最低可容許股價 (元)", value=50.0, step=5.0)
max_price_input = st.sidebar.number_input("最高可容許股價 (元)", value=190.0, step=10.0)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控 (代號,成本)", value="2337,34")

st.title("🏹 2026 獵殺系統 v23.3 - 主升段解鎖版")

# --- A. 庫存檢視模組 ---
st.subheader("📊 庫藏動態與撤退點醒")
if st.button("🔄 刷新庫存狀態"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_data = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="6mo", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="6mo", progress=False)
        # 庫存端放寬股價區間限制以利完整追蹤
        res = execute_sniper_v23(df, tid, tid, 0, trail_pct, 1.0, 9999.0)
        if res:
            p_l = (float(res['現價']) / float(cost) - 1) * 100
            inv_data.append({
                "代號": tid, "現價": res['現價'], "盈虧": f"{round(p_l, 1)}%",
                "撤退線": res['撤退線'], "狀態": res['油門'], "波動力": res['波動力(ATR)'],
                "決策": "✅ 續留" if float(res['現價']) > float(res['撤退線']) else "⚠️ 斷捨離"
            })
    if inv_data:
        df_inv = pd.DataFrame(inv_data)
        df_inv.index = range(1, len(df_inv) + 1)
        st.table(df_inv)

st.markdown("---")

# --- B. 全市場獵殺模組 (純選股輸出，不執行購入) ---
if st.button("🔴 啟動全台股地毯獵殺", type="primary"):
    final_results = []
    tickers, names_map = get_market_map()
    with st.status("📡 掃描 1,800+ 標的，依據 10MA 緩衝進行強勢股過濾...", expanded=True) as status:
        pb = st.progress(0)
        chunk_size = 60
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            pb.progress(min((i + chunk_size) / len(tickers), 1.0))
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False)
                for t in chunk:
                    tid = t.split(".")[0]
                    df_stock = data[t] if len(chunk) > 1 else data
                    # 將自訂價格區間帶入獵殺核心
                    res = execute_sniper_v23(df_stock, tid, names_map.get(tid, tid), vol_limit, trail_pct, min_price_input, max_price_input)
                    
                    if res and res['ATR_VAL'] >= 1.5 and res['勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺篩選完成！", state="complete")

    if final_results:
        st.subheader(f"🏆 全場最強戰力排名 (股價區間: {min_price_input}~{max_price_input} 元)")
        df_res = pd.DataFrame(final_results).sort_values(by="勝率", ascending=False).head(10)
        
        df_res.index = range(1, len(df_res) + 1)
        
        # 格式精確化：強制轉換為浮點數後格式化到小數點第一位，防止字串長度 bug
        df_res['現價'] = df_res['現價'].astype(float).map('{:,.1f}'.format)
        df_res['撤退線'] = df_res['撤退線'].astype(float).map('{:,.1f}'.format)
        df_res['勝率'] = df_res['勝率'].map('{}%'.format)
        
        df_res = df_res.drop(columns=['ATR_VAL'])
        st.table(df_res)
    else:
        st.warning("⚠️ 目前無標的符合動能門檻，請維持空倉避險。建議放寬股價自選區間或調整勝率門檻。")

st.divider()
st.info("💡 **獵人直觀提醒：**\n\n"
        "1. **優化解鎖 (10MA 緩衝)**：此版本計分公式採用 10 日生命均線作為依歸，容許強勢飆股橫盤以盤代跌的震盪，不因短線偏離 5MA 錯失機會。\n"
        "2. **拒絕零股**：在控制台設定好最低與最高股價範圍後，系統將自動放生超出預算的高價零股（如台積電），精準輸出妳買得起一整張的戰力名單。")
