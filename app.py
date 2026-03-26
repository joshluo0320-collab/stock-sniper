import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 強化版名單獲取 (全市場 1,800+ 備援)
# ============================================
@st.cache_data(ttl=86400)
def get_verified_1800_list_v6():
    tickers, names_map = [], {}
    backup = {"2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐", "2330": "台積電"}
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=15, headers={'User-Agent': ua})
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
    if len(tickers) < 10:
        for k, v in backup.items():
            tickers.append(f"{k}.TW")
            names_map[k] = v
    return tickers, names_map

# ============================================
# 2. 核心分析邏輯 (5D / 10D / 預算)
# ============================================
def master_analysis_v19(df, tid, name, vol_gate, trail_p, max_budget):
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    
    last_p = round(float(df['Close'].iloc[-1]), 2)
    # [預算篩選：由輸入框控制]
    if last_p > max_budget: return None

    # 5日與10日分析
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd_slope = (ema_12 - ema_26).diff().iloc[-1]
    
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    if avg_v_5 < vol_gate: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5

    win_5 = 40 + (30 if df['Close'].iloc[-1] > df['Close'].rolling(5).mean().iloc[-1] else -10) + (20 if v_ratio > 1.2 else 0)
    win_10 = 40 + (40 if macd_slope > 0 else -15) + (10 if df['Close'].iloc[-1] > df['Close'].rolling(10).mean().iloc[-1] else 0)
    total_score = int((win_5 * 0.4) + (win_10 * 0.6))
    
    return {
        "名稱": name, "代號": tid, "收盤": last_p,
        "5日勝率": f"{min(98, int(win_5))}%", "10日勝率": f"{min(98, int(win_10))}%",
        "綜合勝率": int(min(98, total_score)),
        "氣勢分析": "🏎️ 衝刺" if macd_slope > 0 else "🐢 盤整",
        "隔日進場區": f"{round(last_p * 0.98, 2)}~{round(last_p * 0.995, 2)}",
        "防守撤退線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. UI 介面
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
# 修正 2: 勝率拉桿改為 5% 一跳
target_win = st.sidebar.slider("🎯 綜合勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

st.sidebar.markdown("---")
st.sidebar.header("💰 資金效率管理")
# 修正 1: 改為數字輸入框
max_budget = st.sidebar.number_input("💸 單張最高預算 (元)", min_value=10, max_value=2000, value=250)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控 (代號,成本)", value="2337,34\n1409,16.5")

st.title("🏹 2026 全景獵殺系統 v19.0")

# --- A. 庫存監控 ---
st.subheader("📊 庫藏動態與止盈管理")
if st.button("🔄 刷新庫存狀態"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_res = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="1y", progress=False)
        res = master_analysis_v19(df, tid, tid, 0, trail_pct, 9999)
        if res:
            p_l = (res['收盤'] / float(cost) - 1) * 100
            inv_res.append({
                "名稱": res['名稱'], "現價": res['收盤'], "盈虧": f"{round(p_l, 2)}%",
                "5日勝率": res['5日勝率'], "撤退線": res['防守撤退線'],
                "決策": "✅ 續留" if res['收盤'] > res['防守撤退線'] else "⚠️ 斷捨離"
            })
    if inv_res: st.table(inv_res)

st.markdown("---")

# --- B. 全市場獵殺 ---
if st.button("🔴 啟動全台股地毯獵殺 (1/1800+)", type="primary"):
    final_results = []
    with st.status(f"📡 獵殺中... (限額: {max_budget}元)", expanded=True) as status:
        tickers, names_map = get_verified_1800_list_v6()
        progress_bar = st.progress(0)
        chunk_size = 40
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=25)
                for t in chunk:
                    tid = t.split(".")[0]
                    df = data[t] if len(chunk) > 1 else data
                    res = master_analysis_v19(df, tid, names_map.get(tid, tid), vol_limit, trail_pct, max_budget)
                    if res and res['綜合勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺完成！", state="complete", expanded=False)

    if final_results:
        st.success(f"📊 報告：符合 {max_budget} 元預算且過濾後的標的共 {len(final_results)} 支。")
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # --- C. 合夥人深度建議 ---
        st.markdown("---")
        st.header("🧠 人生合夥人的盤後點醒")
        best = df_final.iloc[0]
        st.info(f"**【戰略首選：{best['名稱']}】**\n\n"
                f"**數據解析：** 5日勝率 {best['5日勝率']} 顯示短線熱錢正湧入。氣勢分析為 {best['氣勢分析']}。\n\n"
                f"**戰術點醒：** 動態止盈回落設為 **{trail_pct}%**。這代表一旦買入後，若從高點拉回超過此比率，請務必執行「斷捨離」。這不是為了讓你少賺，而是為了保護你的 **19 萬現金** 永遠能在最強的股票上運作。")
    else:
        st.warning(f"⚠️ 在 {max_budget} 元預算內，找不到綜合勝率超過 {target_win}% 的標的。")
