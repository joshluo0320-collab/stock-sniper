import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 核心獵殺邏輯 (v23.2 旗艦修正版)
# ============================================
def execute_sniper_v23(df, tid, name, vol_gate, trail_p, max_budget):
    try:
        if df.empty or len(df) < 40: return None
        
        # 處理 yfinance 多重索引問題並清洗無效數據
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])

        # 基礎現價 (取到小數點第一位)
        last_p = round(float(df['Close'].iloc[-1]), 1) 
        if last_p > max_budget: return None

        # --- [ATR 波動力分析：這是踢除遠傳、亞泥的核心門檻] ---
        tr = pd.concat([
            df['High'] - df['Low'], 
            abs(df['High'] - df['Close'].shift(1)), 
            abs(df['Low'] - df['Close'].shift(1))
        ], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean().iloc[-1]
        volatility_ratio = (atr_14 / last_p) * 100
        
        # 指標計算：5MA 與 MACD 斜率
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ema_12 = df['Close'].ewm(span=12).mean()
        ema_26 = df['Close'].ewm(span=26).mean()
        macd_slope = (ema_12 - ema_26).diff().iloc[-1]
        
        # 20日高點突破判斷
        high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
        is_break = last_p > high_20
        
        # 量比計算
        avg_v_5 = df['Volume'].tail(5).mean() / 1000
        v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5 if avg_v_5 > 0 else 0

        # 綜合勝率評分
        win_score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        
        # 動態撤退線 (取到小數點第一位)
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
# 2. 名單抓取工具
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
# 3. Streamlit UI 戰略介面 (PM 規格)
# ============================================
st.set_page_config(page_title="獵殺系統 v23.2", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
# 操作調整 1-3：修正步進單位
target_win = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 15.0, 5.0, step=1.0)
max_budget = st.sidebar.number_input("💸 單張預算上限 (元)", value=250)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控 (代號,成本)", value="2337,34")

st.title("🏹 2026 獵殺系統 v23.2 - 戰力排名版")

# --- A. 庫存檢視模組 ---
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
            p_l = (float(res['現價']) / float(cost) - 1) * 100
            inv_data.append({
                "代號": tid, "現價": res['現價'], "盈虧": f"{round(p_l, 1)}%",
                "撤退線": res['撤退線'], "狀態": res['油門'], "波動力": res['波動力(ATR)'],
                "決策": "✅ 續留" if float(res['現價']) > float(res['撤退線']) else "⚠️ 斷捨離"
            })
    if inv_data:
        df_inv = pd.DataFrame(inv_data)
        df_inv.index = range(1, len(df_inv) + 1) # 強制顯示為 1, 2, 3...
        st.table(df_inv)

st.markdown("---")

# --- B. 全市場獵殺模組 (1.5% ATR 門檻) ---
if st.button("🔴 啟動全台股地毯獵殺", type="primary"):
    final_results = []
    tickers, names_map = get_market_map()
    with st.status("📡 掃描 1,800+ 標的，過濾 ATR < 1.5% 之牛皮股...", expanded=True) as status:
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
                    
                    # 戰略過濾：ATR 必須大於 1.5% (踢掉亞泥、遠傳)
                    if res and res['ATR_VAL'] >= 1.5 and res['勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺篩選完成！", state="complete")

    if final_results:
        st.subheader("🏆 全場最強戰力排名 (已過濾牛皮股)")
        # 1. 轉為 DataFrame 並排序
        df_res = pd.DataFrame(final_results).sort_values(by="勝率", ascending=False).head(10)
        
        # 2. 強制排名編號：1, 2, 3...
        df_res.index = range(1, len(df_res) + 1)
        
        # 3. 修正顯示：價格到小數點第一位，勝率加上 %
        df_res['現價'] = df_res['現價'].map('{:,.1f}'.format)
        df_res['撤退線'] = df_res['撤退線'].map('{:,.1f}'.format)
        df_res['勝率'] = df_res['勝率'].map('{}%'.format)
        
        # 4. 移除隱藏計算欄位
        df_res = df_res.drop(columns=['ATR_VAL'])
        
        st.table(df_res)
    else:
        st.warning("⚠️ 目前無標的符合動能門檻，請維持空倉避險。")

st.divider()
# --- 底部圖例說明 ---
st.info("💡 **獵人直觀提醒：**\n\n"
        "1. **左側排名**：1 代表勝率與動能綜合評分最高的第一名標的。\n"
        "2. **ATR (波動力)**：代表標的每日震幅。低於 1.5% (如遠傳、亞泥) 會自動被系統放生。\n"
        "3. **⚠️ 隔日沖**：若出現在風險欄位，代表籌碼過熱，開盤切勿市價追高，建議等回測進場區。\n\n"
        "**圖示說明：**\n"
        "🏎️ **加速**：多頭動能強勁 | 🐢 **減速**：力道轉弱\n"
        "🛣️ **無壓**：創新高無套牢盤 | 🚧 **有牆**：上方仍有賣壓\n"
        "⛽ **爆量**：主力點火訊號 | 🚗 **正常**：波動溫和")
