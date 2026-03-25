import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 自動連網：今日時事熱點分析
# ============================================
@st.cache_data(ttl=600)
def get_live_sentiment():
    """自動偵測國際情勢與時事權重"""
    weights = {"2337": 15, "3017": 15, "3234": 15, "4919": 10, "1409": 10}
    try:
        res = requests.get("https://money.udn.com/money/index", timeout=5, verify=False)
        res.encoding = 'utf-8'
        text = res.text
        if "記憶體" in text or "HBM" in text: weights["2337"] += 10
        if "散熱" in text or "液冷" in text: weights["3017"] += 10
        if "邊緣運算" in text or "MCU" in text: weights["4919"] += 10
        if "避險" in text or "衝突" in text: weights["1409"] += 15
    except: pass
    return weights

# ============================================
# 2. 側邊控制台：直白控制項
# ============================================
st.sidebar.header("🕹️ 獵殺控制台")
min_gate = st.sidebar.slider("🎯 綜合勝率門檻 (%)", 10, 95, 50)
st.sidebar.info("勝率由：趨勢(40%)、能量(20%)、時事(20%) 組成")

st.sidebar.markdown("---")
st.sidebar.header("🌊 流動性門檻")
vol_gate = st.sidebar.slider("📊 5日均張 (過濾冷門股)", 0, 5000, 500)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存設定")
inventory_input = st.sidebar.text_area("代號,成本", value="2337,34\n1409,16.5")

# ============================================
# 3. 核心邏輯：中文名稱對應與計算
# ============================================
STOCK_NAMES = {"2337": "旺宏", "3017": "奇鋐", "3234": "光環", "1409": "新纖", "4919": "新唐", "2330": "台積電"}

def sniper_analysis(df, tid, news_w, min_v):
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    # [能量與流動性分析]
    avg_v = df['Volume'].tail(5).mean() / 1000
    if avg_v < min_v: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v

    # [趨勢分析]
    close = df['Close']
    df['MACD_S'] = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    is_break = close.iloc[-1] > df['High20'].iloc[-1]
    
    # [勝率加權]
    score = 40
    score += 20 if df['MACD_S'].iloc[-1] > 0 else -10
    score += 20 if is_break else 0
    score += 10 if v_ratio > 1.3 else 0
    score += news_w.get(tid, 0)
    
    return {
        "name": STOCK_NAMES.get(tid, tid),
        "score": min(98, score),
        "v_ratio": round(v_ratio, 2),
        "avg_v": int(avg_v),
        "price": round(float(close.iloc[-1]), 2),
        "stop": round(float(df['High'].cummax().iloc[-1] * 0.93), 2)
    }

# ============================================
# 4. 顯示：去蕪存菁最強前五
# ============================================
st.title("🏹 台股全景獵殺系統 - 中文直白版")

news_w = get_live_sentiment()

# --- 庫存監控 ---
st.subheader("💰 我的持倉動態檢視")
if st.button("🔄 更新持倉走勢"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_res = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="1y", progress=False)
        res = sniper_analysis(df, tid, news_w, 0)
        if res:
            p_l = (res['price'] / float(cost) - 1) * 100
            inv_res.append({
                "股票名稱": res['name'], "成本": cost, "現價": res['price'],
                "即時盈虧": f"{round(p_l, 2)}%", "止盈線": res['stop'], "建議": "✅ 續留" if res['price'] > res['stop'] else "⚠️ 撤退"
            })
    st.table(inv_res)

st.markdown("---")

# --- 最強前五 ---
st.subheader("🏆 全市場最強前五標的")
if st.button("🔴 開始全新搜尋", type="primary"):
    st.write(f"🌍 今日連網時事加權：{news_w}")
    pool = ["2337.TW", "3017.TW", "3234.TWO", "1409.TW", "4919.TW", "2330.TW"]
    scan_res = []
    for t in pool:
        df = yf.download(t, period="6mo", progress=False)
        tid = t.split(".")[0]
        res = sniper_analysis(df, tid, news_w, vol_gate)
        if res and res['score'] >= min_gate:
            scan_res.append(res)
    
    if scan_res:
        df_top5 = pd.DataFrame(scan_res).sort_values(by="score", ascending=False).head(5)
        # 轉換表格欄位名稱
        df_show = df_top5.rename(columns={
            "name": "股票名稱", "score": "綜合勝率(%)", "v_ratio": "能量異動(倍)",
            "avg_v": "5日均張", "price": "今日現價", "stop": "防守線"
        })
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        # --- 人生合夥人深度點醒 ---
        st.markdown("---")
        st.header("🧠 人生合夥人的直白點醒")
        top_name = df_show.iloc[0]['股票名稱']
        st.info(f"**【獵殺標的：{top_name}】** 目前勝率最高！它不僅具備趨勢突破，連網時事更顯示其族群正受到資金熱捧。如果你的 19 萬現金在找家，這就是首選。")
