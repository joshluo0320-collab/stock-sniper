import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 戰略核心：自動時事與數據模組
# ============================================
@st.cache_data(ttl=600)
def get_live_news_weights():
    """自動連網更新時事權重"""
    weights = {"2337": 15, "3234": 15, "1409": 10, "4919": 10, "3017": 15}
    try:
        res = requests.get("https://money.udn.com/money/index", timeout=5, verify=False)
        res.encoding = 'utf-8'
        headlines = res.text
        if "記憶體" in headlines or "Rubin" in headlines: weights["2337"] += 10
        if "矽光子" in headlines or "CPO" in headlines: weights["3234"] += 10
        if "散熱" in headlines or "液冷" in headlines: weights["3017"] += 10
        if "戰爭" in headlines or "美伊" in headlines: weights["1409"] += 15
    except: pass
    return weights

def calculate_master_logic(df, tid, news_w, vol_gate):
    """核心分析邏輯：趨勢、能量、突破、流動性"""
    if df.empty or len(df) < 20: return None
    
    # 處理 yfinance 可能的 MultiIndex 欄位
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    # [流動性與 5 日均張] - 確保單一數值比較，修復 ValueError
    avg_vol_5d_lots = (df['Volume'].rolling(5).mean().iloc[-1]) / 1000
    if avg_vol_5d_lots < vol_gate: return None
    
    vol_ratio = (df['Volume'].iloc[-1] / 1000) / avg_vol_5d_lots

    # [趨勢與突破]
    close = df['Close']
    df['MACD_S'] = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    is_breakout = close.iloc[-1] > df['High20'].iloc[-1]
    
    # [綜合勝率計算]
    score = 40
    score += 20 if df['MACD_S'].iloc[-1] > 0 else -10
    score += 20 if is_breakout else 0
    score += 10 if vol_ratio > 1.2 else 0
    score += news_w.get(tid, 0)
    
    return {
        "score": min(98, score),
        "vol_5d": int(avg_vol_5d_lots),
        "vol_ratio": round(vol_ratio, 2),
        "status": "🚀 突破" if is_breakout else "盤整",
        "price": round(float(close.iloc[-1]), 2),
        "stop": round(float(df['High'].cummax().iloc[-1] * (1 - trail_pct/100)), 2)
    }

# ============================================
# 2. UI 佈局：控制台與庫存
# ============================================
st.sidebar.header("🕹️ 勝率控制台")
min_gate = st.sidebar.slider("🎯 綜合勝率門檻 (%)", 10, 95, 50)
trail_pct = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

st.sidebar.markdown("---")
st.sidebar.header("📊 流動性過濾")
min_vol_lots = st.sidebar.slider("🌊 5日均張門檻", 0, 5000, 500)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫藏設定")
inventory_input = st.sidebar.text_area("格式: 代號,成本", value="2337,34\n1409,16.5")

# ============================================
# 3. 執行介面：庫存 -> 掃描 -> 合夥人建議
# ============================================
st.title("🏹 2026 全景獵殺儀錶板 - 斷捨離實戰版")

news_weights = get_live_news_weights()

# --- A. 我的庫藏監控 ---
st.subheader("💰 我的庫藏動態 (連動最新走勢)")
if st.button("🔄 刷新庫存與止盈線"):
    inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
    inv_results = []
    for tid, cost in inv_list:
        tid = tid.strip()
        df = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df.empty: df = yf.download(f"{tid}.TWO", period="1y", progress=False)
        if not df.empty:
            res = calculate_master_logic(df, tid, news_weights, 0) # 庫存不限流量
            if res:
                p_l = (res['price'] / float(cost) - 1) * 100
                inv_results.append({
                    "代號": tid, "成本": cost, "現價": res['price'],
                    "累計盈虧": f"{round(p_l, 2)}%", "止盈線": res['stop'],
                    "決策": "✅ 續留" if res['price'] > res['stop'] else "⚠️ 撤退"
                })
    if inv_results:
        st.table(pd.DataFrame(inv_results))

st.markdown("---")

# --- B. 全市場去蕪存菁 (最強前五) ---
st.subheader(f"🏆 全市場最強前五標的 (門檻: {min_gate}%)")
if st.button("🔴 啟動全方位時事掃描", type="primary"):
    st.write(f"🌍 今日連網時事權重已載入：{news_weights}")
    
    # 範例掃描池 (實務上可串接 get_full_market_list)
    pool = ["2337.TW", "3017.TW", "3234.TWO", "1409.TW", "4919.TW", "2383.TW", "2330.TW"]
    
    scan_results = []
    bar = st.progress(0)
    for i, t in enumerate(pool):
        bar.progress((i + 1) / len(pool))
        df = yf.download(t, period="6mo", progress=False)
        tid = t.split(".")[0]
        res = calculate_master_logic(df, tid, news_weights, min_vol_lots)
        if res and res['score'] >= min_gate:
            scan_results.append({
                "代號": tid, "綜合勝率": res['score'], "5日均張": res['vol_5d'],
                "能量異動": f"{res['vol_ratio']}倍", "狀態": res['status'], "現價": res['price']
            })
    
    if scan_results:
        df_top5 = pd.DataFrame(scan_results).sort_values(by="綜合勝率", ascending=False).head(5)
        st.dataframe(df_top5, use_container_width=True, hide_index=True)
        
        # --- C. 人生合夥人的建議區 ---
        st.markdown("---")
        st.header("🧠 人生合夥人的戰略建議")
        col1, col2 = st.columns(2)
        with col1:
            st.info("**🎯 攻擊目標分析**\n\n" + 
                    f"今日最強為 **{df_top5.iloc[0]['代號']}**，勝率高達 {df_top5.iloc[0]['綜合勝率']}%。\n" +
                    f"能量異動 {df_top5.iloc[0]['能量異動']} 代表資金強烈認同，適合 19 萬現金佈局。")
        with col2:
            st.warning("**🛡️ 防禦策略提醒**\n\n" + 
                       "若大盤受國際情勢影響震盪，請守穩庫存止盈線。\n" +
                       "**新纖 (1409)** 雖慢，但它是你目前的資金避風港。")
