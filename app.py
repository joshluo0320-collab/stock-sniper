import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 核心獵殺邏輯 (v23.3 科技狂潮解鎖版)
# ============================================
def execute_sniper_v23(df, tid, name, vol_gate, trail_p, min_price, max_price):
    try:
        if df.empty or len(df) < 40: return None
        
        # 處理 yfinance 多重索引問題並清洗無效數據
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])

        # 基礎現價 (嚴格四捨五入到整數)
        last_p = int(round(float(df['Close'].iloc[-1]), 0))
        
        # 股價範圍過濾：在解鎖動能的同時，依然鋼鐵般守住整張交易的價格防線
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
        ma10 = df['Close'].rolling(10).mean().iloc[-1]
        
        ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_slope = (ema_12 - ema_26).diff().iloc[-1]
        
        # 20日高點突破判斷
        high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
        is_break = last_p > high_20
        
        # 10MA 乖離率計算
        bias_10 = ((last_p / ma10) - 1) * 100

        # --- [🚨 戰略解鎖：依據妳的決策，將 10MA 追高阻斷門檻放寬至 15%] ---
        if bias_10 > 15.0: return None

        # 量比計算
        avg_v_5 = df['Volume'].tail(5).mean() / 1000
        v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5 if avg_v_5 > 0 else 0

        # 計分公式 (維持 10MA 強勢主升段緩衝計分)
        win_score = int(((50 if last_p > ma10 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        if win_score < 0: win_score = 0
        if win_score > 100: win_score = 100
        
        # 修正版動態撤退線：鎖定 20 日內最高價，避免被歷史幽靈高點綁架
        recent_high = df['High'].tail(20).max()
        dynamic_trail = min(max(trail_p, 3.5), 7.0) 
        withdrawal_line = int(round(float(recent_high * (1 - dynamic_trail/100)), 0))
        
        # 撤退線防呆：若極端大於現價，強迫以 10MA 為防守底線
        if withdrawal_line >= last_p:
            withdrawal_line = int(round(ma10, 0))

        # 隔日沖風險辨識
        today_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) * 100
        risk_label = "⚠️ 隔日沖" if (v_ratio > 2.8 and today_ret > 6) else "✅ 穩健"

        return {
            "名稱": name, "代號": tid, "勝率": win_score,
            "現價": last_p, "撤退線": withdrawal_line, 
            "波動力(ATR)": f"{round(volatility_ratio, 2)}%",
            "油門": "🏎️ 加速" if macd_slope > 0 else "🐢 減速",
            "能量": "⛽ 爆量" if v_ratio > 1.5 else "🚗 正常",
            "路況": "🛣️ 無壓" if is_break else "🚧 有牆",
            "建議進場區": f"{int(round(last_p * 0.98, 0))}~{int(round(last_p * 0.995, 0))}",
            "風險": risk_label,
            "ATR_VAL": volatility_ratio 
        }
    except: return None

# ============================================
# 2. 名單抓取工具 (1800+ 完整台股地圖)
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
                    if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
                        suffix = ".TW" if "strMode=2" in url else ".TWO"
                        tickers.append(f"{raw[0]}{suffix}")
                        names_map[raw[0]] = raw[1]
        except: continue
    return tickers, names_map

# ============================================
# 3. Streamlit UI 戰略介面
# ============================================
st.set_page_config(page_title="獵殺系統 v23.3", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台 v23.3")
target_win = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 15.0, 5.0, step=1.0)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 拒絕零股！股價自選區間")
min_price_input = st.sidebar.number_input("最低可容許股價 (元)", value=50.0, step=5.0)
max_price_input = st.sidebar.number_input("最高可容許股價 (元)", value=150.0, step=10.0)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控 (代號,成本)", value="2337,34")

st.title("🏹 2026 獵殺系統 v23.3 - 科技狂潮解鎖版")

# --- A. 庫存檢視模組 ---
st.subheader("📊 庫藏動態與撤退點醒")
if st.button("🔄 刷新庫存狀態"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_data = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="6mo", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="6mo", progress=False)
        res = execute_sniper_v23(df, tid, tid, 0, trail_pct, 1.0, 9999.0)
        if res:
            p_l = (float(res['現價']) / float(cost) - 1) * 100
            inv_data.append({
                "代號": tid, "現價": int(res['現價']), "盈虧": f"{round(p_l, 1)}%",
                "撤退線": int(res['撤退線']), "狀態": res['油門'], "波動力": res['波動力(ATR)'],
                "決策": "✅ 續留" if float(res['現價']) > float(res['撤退線']) else "⚠️ 斷捨離"
            })
    if inv_data:
        df_inv = pd.DataFrame(inv_data)
        df_inv.index = range(1, len(df_inv) + 1)
        st.table(df_inv)

st.markdown("---")

# --- B. 全市場獵殺模組 ---
if st.button("🔴 啟動全台股地毯獵殺", type="primary"):
    final_results = []
    tickers, names_map = get_market_map()
    with st.status(f"📡 正在地毯式掃描全台股標的... 確保讀取數量：{len(tickers)} 檔", expanded=True) as status:
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
                    res = execute_sniper_v23(df_stock, tid, names_map.get(tid, tid), vol_limit, trail_pct, min_price_input, max_price_input)
                    
                    if res and res['ATR_VAL'] >= 1.5 and res['勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 全台股地毯獵殺篩選完成！", state="complete")

    if final_results:
        st.subheader(f"🏆 全場最強戰力排名 (股價區間: {int(min_price_input)}~{int(max_price_input)} 元，解鎖 15% 乖離)")
        df_res = pd.DataFrame(final_results).sort_values(by="勝率", ascending=False).head(10)
        df_res.index = range(1, len(df_res) + 1)
        
        df_res['現價'] = df_res['現價'].astype(float).map('{:,.0f}'.format)
        df_res['撤退線'] = df_res['撤退線'].astype(float).map('{:,.0f}'.format)
        df_res['勝率'] = df_res['勝率'].map('{}%'.format)
        
        df_res = df_res.drop(columns=['ATR_VAL'])
        st.table(df_res)
    else:
        st.warning("⚠️ 目前無標的符合動能門檻，請維持空倉避險。")
