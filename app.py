import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用不安全請求警告（針對部分環境抓取證交所名單時使用）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 核心獵殺邏輯 (v23.2 旗艦版)
# ============================================
def execute_sniper_v23(df, tid, name, vol_gate, trail_p, max_budget):
    try:
        if df.empty or len(df) < 40: return None
        
        # 解決 yfinance MultiIndex 與缺失值問題
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])

        # 基礎價格過濾
        last_p = round(float(df['Close'].iloc[-1]), 1) 
        if last_p > max_budget: return None

        # --- [ATR 波動力分析：踢除牛皮股的關鍵] ---
        tr = pd.concat([
            df['High'] - df['Low'], 
            abs(df['High'] - df['Close'].shift(1)), 
            abs(df['Low'] - df['Close'].shift(1))
        ], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean().iloc[-1]
        volatility_ratio = (atr_14 / last_p) * 100
        
        # 指標計算
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ema_12 = df['Close'].ewm(span=12).mean()
        ema_26 = df['Close'].ewm(span=26).mean()
        macd_slope = (ema_12 - ema_26).diff().iloc[-1]
        
        high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
        is_break = last_p > high_20
        
        avg_v_5 = df['Volume'].tail(5).mean() / 1000
        v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5 if avg_v_5 > 0 else 0

        # 勝率評分
        win_score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        
        # 動態撤退線
        dynamic_trail = min(max(trail_p, 3.5), 7.0) 
        withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - dynamic_trail/100)), 1)

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
            "建議區": f"{round(last_p * 0.98, 1)}~{round(last_p * 0.995, 1)}",
            "風險": risk_label,
            "ATR_VAL": volatility_ratio # 用於過濾，不顯示
        }
    except: return None

# ============================================
# 2. 名單抓取與快取
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
                        tickers.append(f"{raw[0]}{suffix}"); names_map[raw[0]] = raw[1]
        except: continue
    return tickers, names_map

# ============================================
# 3. Streamlit UI 戰略中樞
# ============================================
st.set_page_config(page_title="獵殺系統 v23.2", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
target_win = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 15.0, 5.0, step=1.0)
max_budget = st.sidebar.number_input("💸 單張預算上限 (元)", value=250)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控 (代號,成本)\n例如: 2337,34", value="2337,34")

st.title("🏹 2026 獵殺系統 v23.2 - 戰力排名版")

# --- A. 庫存監控模組 ---
st.subheader("📊 庫藏動態與撤退點醒")
if st.button("🔄 刷新庫存狀態"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_data = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="6mo", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="6mo", progress=False)
        res = execute_sniper_v23(df, tid, tid, 0, trail_pct, 9999)
        if res:
            p_l = (res['現價'] / float(cost) - 1) * 100
            inv_data.append({
                "代號": tid, "現價": res['現價'], "盈虧": f"{round(p_l, 1)}%",
                "撤退線": res['撤退線'], "狀態": res['油門'], "波動力": res['波動力(ATR)'],
                "建議": "✅ 續留" if res['現價'] > res['撤退線'] else "⚠️ 斷捨離"
            })
    if inv_data:
        df_inv = pd.DataFrame(inv_data)
        df_inv.index = range(1, len(df_inv) + 1) # 強制重新編號為名次 1, 2, 3...
        st.table(df_inv)

st.markdown("---")

# --- B. 全市場獵殺模組 ---
if st.button("🔴 啟動全台股地毯獵殺 (1/1800+)", type="primary"):
    final_results = []
    tickers, names_map = get_market_map()
    with st.status("📡 搜尋符合波動力 > 1.5% 之標的...", expanded=True) as status:
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
                    res = execute_sniper_v23(df_stock, tid, names_map.get(tid, tid), vol_limit, trail_pct, max_budget)
                    
                    # --- [戰略過濾：ATR < 1.5% 視為牛皮股踢除] ---
                    if res and res['ATR_VAL'] >= 1.5 and res['勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺篩選完成！", state="complete")

    if final_results:
        st.subheader("🏆 全場最強戰力 Top 10 (已過濾牛皮股)")
        # 排序並取前 10
        df_res = pd.DataFrame(final_results).sort_values(by="勝率", ascending=False).head(10)
        
        # 格式修正：名次重新編號
        df_res.index = range(1, len(df_res) + 1)
        
        # 格式修正：現價與撤退線顯示至小數點第一位
        df_res['現價'] = df_res['現價'].map('{:,.1f}'.format)
        df_res['撤退線'] = df_res['撤退線'].map('{:,.1f}'.format)
        
        # 隱藏計算用欄位，將勝率加上百分比符號
        df_res['勝率'] = df_res['勝率'].map('{}%'.format)
        df_res = df_res.drop(columns=['ATR_VAL'])
        
        st.table(df_res)
    else:
        st.warning("⚠️ 目前市場標的皆不符合 1.5% 波動動能門檻，請維持空倉。")

st.divider()
# --- 底部圖例說明 ---
st.info("💡 **獵人系統操作提醒：**\n\n"
        "1. **左側數字**：代表當次篩選後的『戰力排名』，1 為最強。\n"
        "2. **ATR (波動力)**：代表標的每日震盪幅度。低於 1.5% (如亞泥、中鋼) 會自動被系統放生。\n"
        "3. **⚠️ 隔日沖**：若出現在風險欄位，代表該股目前籌碼過熱，明日開盤切勿市價追高。\n\n"
        "**圖示說明：**\n"
        "🏎️ **加速**：動態強勁 | 🐢 **減速**：力道放緩\n"
        "🛣️ **無壓**：創新高無套牢 | 🚧 **有牆**：上方有賣壓\n"
        "⛽ **爆量**：主力點火 | 🚗 **正常**：波動溫和")
