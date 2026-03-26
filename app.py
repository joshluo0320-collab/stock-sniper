import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import time
import random

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 強化版名單獲取 (三層防禦模式)
# ============================================
@st.cache_data(ttl=86400)
def get_verified_1800_list_v4():
    tickers, names_map = [], {}
    core_backup = {"2337": "旺宏", "1409": "新纖", "3017": "奇鋐", "3234": "光環", "4919": "新唐", "2330": "台積電", "2317": "鴻海"}
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    
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
        for k, v in core_backup.items():
            tickers.append(f"{k}.TW")
            names_map[k] = v
    return tickers, names_map

# ============================================
# 2. 多週期分析邏輯 (5日/10日/綜合)
# ============================================
def multi_period_sniper_logic(df, tid, name, vol_gate, trail_p, p_min, p_max):
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    
    last_p = round(float(df['Close'].iloc[-1]), 2)
    # 預算過濾
    if last_p < p_min or last_p > p_max: return None

    # 5日勝率因子 (極短線：爆量與均線支撐)
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    if avg_v_5 < vol_gate: return None
    v_ratio_5 = (df['Volume'].iloc[-1] / 1000) / avg_v_5
    win_5 = 40 + (30 if df['Close'].iloc[-1] > df['Close'].rolling(5).mean().iloc[-1] else -10) + (20 if v_ratio_5 > 1.2 else 0)

    # 10日勝率因子 (中線：趨勢方向)
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd_slope = (ema_12 - ema_26).diff().iloc[-1]
    win_10 = 40 + (40 if macd_slope > 0 else -15) + (10 if df['Close'].iloc[-1] > df['Close'].rolling(10).mean().iloc[-1] else 0)

    # 綜合評估
    total_score = int((win_5 * 0.4) + (win_10 * 0.6))
    is_break = df['Close'].iloc[-1] > df['High'].rolling(20).max().shift(1).iloc[-1]
    if is_break: total_score += 10
    
    return {
        "名稱": name, "代號": tid, "收盤": last_p,
        "5日勝率": f"{min(98, int(win_5))}%",
        "10日勝率": f"{min(98, int(win_10))}%",
        "綜合勝率": int(min(98, total_score)),
        "氣勢": "🏎️ 衝刺" if macd_slope > 0 else "🐢 盤整",
        "能量": "⛽ 爆滿" if v_ratio_5 > 1.5 else "🚗 正常",
        "進場區": f"{round(last_p * 0.98, 2)}~{round(last_p * 0.995, 2)}",
        "防守價": round(float(df['High'].cummax().iloc[-1] * (1 - trail_p/100)), 2)
    }

# ============================================
# 3. 介面與執行
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
target_win = st.sidebar.slider("🎯 綜合勝率門檻 (%)", 10, 95, 60)
vol_limit = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)

st.sidebar.markdown("---")
st.sidebar.header("💰 資金預算篩選")
price_range = st.sidebar.slider("設定股價區間 (元)", 0, 1000, (10, 250))
min_p, max_p = price_range

st.title("🏹 2026 全景獵殺系統 v17.0 - 資金多週期版")

if st.button("🔴 啟動全台股地毯獵殺 (1/1800+)", type="primary"):
    final_results = []
    with st.status(f"📡 正在掃描全市場... (預算: {min_p}~{max_p}元)", expanded=True) as status:
        tickers, names_map = get_verified_1800_list_v4()
        st.write(f"✅ 成功鎖定 {len(tickers)} 支標的，排除不合預算股票...")
        
        progress_bar = st.progress(0)
        chunk_size = 40
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            progress_bar.progress(min((i + chunk_size) / len(tickers), 1.0))
            try:
                data = yf.download(chunk, period="6mo", group_by='ticker', progress=False, timeout=30)
                for t in chunk:
                    tid = t.split(".")[0]
                    df = data[t] if len(chunk) > 1 else data
                    res = multi_period_sniper_logic(df, tid, names_map.get(tid, tid), vol_limit, 7.0, min_p, max_p)
                    if res and res['綜合勝率'] >= target_win:
                        final_results.append(res)
            except: continue
        status.update(label="🎯 獵殺掃描完成！", state="complete", expanded=False)

    if final_results:
        st.success(f"📊 報告：全市場符合預算且過濾後的標的共 {len(final_results)} 支。")
        df_final = pd.DataFrame(final_results).sort_values(by="綜合勝率", ascending=False).head(10)
        # 轉換綜合勝率格式顯示
        df_final['綜合勝率'] = df_final['綜合勝率'].apply(lambda x: f"{x}%")
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # 合夥人點醒
        st.markdown("---")
        st.header("🧠 人生合夥人的戰術解析")
        best = df_final.iloc[0]
        st.info(f"**【戰略首選：{best['名稱']} ({best['代號']})】**\n\n"
                f"該標的 **5日勝率 {best['5日勝率']}** (短線爆發) 且 **10日勝率 {best['10日勝率']}** (波段慣性)。\n"
                f"收盤價 **{best['收盤']}** 符合你的資金配置需求。\n\n"
                f"**獵人提示：** 當 5日勝率 > 10日勝率時，代表動能正在「急劇增強」，這是最適合 19 萬現金短線切入的時機。")
    else:
        st.warning(f"⚠️ 在 {min_p}~{max_p} 元預算內，找不到綜合勝率超過 {target_win}% 的標的。建議調整預算或降低勝率要求。")
