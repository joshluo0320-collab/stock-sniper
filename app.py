import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 自動連網：今日時事與國際情勢權重
# ============================================
@st.cache_data(ttl=3600)
def get_market_news_weights():
    """自動偵測國際熱點：AI算力、美伊衝突、半導體循環"""
    weights = {"2337": 15, "3017": 15, "3234": 15, "4919": 10, "1409": 10}
    try:
        res = requests.get("https://money.udn.com/money/index", timeout=5, verify=False)
        res.encoding = 'utf-8'
        text = res.text
        if "記憶體" in text or "HBM" in text: weights["2337"] += 10
        if "散熱" in text or "液冷" in text: weights["3017"] += 10
        if "邊緣運算" in text or "MCU" in text: weights["4919"] += 10
        if "衝突" in text or "避險" in text: weights["1409"] += 15
    except: pass
    return weights

# ============================================
# 2. 核心邏輯：將專業指標轉化為「白話分析」
# ============================================
STOCK_NAMES = {"2337": "旺宏", "3017": "奇鋐", "3234": "光環", "1409": "新纖", "4919": "新唐", "2330": "台積電"}

def get_plain_analysis(df, tid, news_w, min_v):
    if df.empty or len(df) < 25: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    # [能量數據：油箱滿不滿]
    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < min_v: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v
    vol_text = "⛽ 油箱爆滿 (主力進場)" if v_ratio > 1.5 else "🚗 油量正常 (平穩)"

    # [趨勢數據：油門踩多深]
    close = df['Close']
    dif = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff().iloc[-1]
    trend_text = "🏎️ 全油門衝刺" if dif > 0 else "🐢 慢速爬行"

    # [突破點數據：前面有牆嗎]
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = close.iloc[-1] > high_20
    wall_text = "🛣️ 前方無障礙 (已超車)" if is_break else "🚧 前方有牆 (盤整中)"
    
    # [勝率與建議進場價]
    score = 40 + (25 if dif > 0 else -10) + (20 if is_break else 0) + (10 if v_ratio > 1.2 else 0) + news_w.get(tid, 0)
    last_p = round(float(close.iloc[-1]), 2)
    entry_low = round(last_p * 0.98, 2)  # 回測2%
    entry_high = round(last_p * 0.995, 2) # 回測0.5%
    
    return {
        "股票名稱": STOCK_NAMES.get(tid, tid),
        "綜合勝率": f"{min(98, score)}%",
        "氣勢分析": trend_text,
        "路況分析": wall_text,
        "能量分析": vol_text,
        "今日收盤": last_p,
        "隔日建議進場區": f"{entry_low} ~ {entry_high}",
        "撤退防守線": round(float(df['High'].cummax().iloc[-1] * (1 - trail_pct/100)), 2)
    }

# ============================================
# 3. UI 介面佈局
# ============================================
st.sidebar.header("🕹️ 戰略控制台")
min_score = st.sidebar.slider("🎯 最低勝率門檻", 10, 95, 50)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)
vol_gate = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)

inventory_input = st.sidebar.text_area("📋 庫存: 代號,成本", value="2337,34\n1409,16.5")

st.title("🏹 2026 全景獵殺系統 - 盤後佈局版")

news_w = get_market_news_weights()

# --- 庫存狀態 ---
st.subheader("💰 庫藏動態與撤退點醒")
if st.button("🔄 刷新庫藏走勢"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_data = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="1y", progress=False)
        res = get_plain_analysis(df, tid, news_w, 0)
        if res:
            p_l = (res['今日收盤'] / float(cost) - 1) * 100
            inv_data.append({
                "股票名稱": res['股票名稱'], "即時盈虧": f"{round(p_l, 2)}%",
                "現價": res['今日收盤'], "防守價": res['撤退防守線'],
                "白話點醒": "✅ 趨勢極強，安心續抱" if res['今日收盤'] > res['撤退防守線'] else "⚠️ 警報響起，準備離場"
            })
    st.table(inv_data)

st.markdown("---")

# --- 盤後最強前五與進場價 ---
st.subheader("🏆 隔日獵殺：最強前五標的與進場價")
if st.button("🔴 啟動全方位時事掃描", type="primary"):
    pool = ["2337.TW", "3017.TW", "3234.TWO", "1409.TW", "4919.TW", "2383.TW", "2330.TW"]
    scan_res = []
    for t in pool:
        df = yf.download(t, period="6mo", progress=False)
        tid = t.split(".")[0]
        res = get_plain_analysis(df, tid, news_w, vol_gate)
        if res and int(res['綜合勝率'].replace('%','')) >= min_score:
            scan_res.append(res)
    
    if scan_res:
        df_top5 = pd.DataFrame(scan_res).sort_values(by="綜合勝率", ascending=False).head(5)
        st.dataframe(df_top5, use_container_width=True, hide_index=True)

        # --- 人生合夥人的直白建議區 ---
        st.markdown("---")
        st.header("🧠 人生合夥人的直白戰術建議")
        top_pick = df_top5.iloc[0]
        st.info(f"**【戰術首選：{top_pick['股票名稱']}】**\n\n" + 
                f"這支股票目前 **{top_pick['氣勢分析']}**，且 **{top_pick['路況分析']}**。\n" +
                f"明天建議在 **{top_pick['隔日建議進場區']}** 之間埋伏。如果開盤直接衝太高，寧可不買，也不要追高！\n\n" +
                f"**時事提醒：** 目前國際焦點在 AI 算力與地緣政治，這支股票剛好站在風口上，贏面極大。")
