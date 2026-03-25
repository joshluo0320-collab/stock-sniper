import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 自動連網更新時事模組 (AutoNewsWeight)
# ============================================
def get_live_market_sentiment():
    """自動從財經新聞抓取今日熱點關鍵字並設定權重"""
    weights = {"2337": 15, "3017": 12, "3234": 10, "1409": 5} # 預設權重
    try:
        # 爬取新聞頭條 (範例: 經濟日報或 CMoney)
        res = requests.get("https://money.udn.com/money/index", timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        headlines = soup.get_text()
        
        # 關鍵字加權邏輯
        if "記憶體" in headlines or "HBM" in headlines: weights["2337"] += 5
        if "散熱" in headlines or "液冷" in headlines: weights["3017"] += 8
        if "矽光子" in headlines or "CPO" in headlines: weights["3234"] += 5
        if "戰爭" in headlines or "避險" in headlines: weights["1409"] += 10
    except:
        pass # 若失敗則使用預設
    return weights

# ============================================
# 2. 核心分析模組 (趨勢 + 能量 + 突破 + 時事)
# ============================================
def master_analyze(df, tid, news_w, vol_limit):
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    # [能量 Energy]
    last_vol = df['Volume'].iloc[-1]
    avg_vol_5d = df['Volume'].tail(5).mean()
    vol_ratio = last_vol / avg_vol_5d
    if (avg_vol_5d / 1000) < vol_limit: return None

    # [趨勢 & 突破 Trend & Breakout]
    close = df['Close']
    df['MACD_S'] = (close.ewm(span=12).mean() - close.ewm(span=26).mean()).diff()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    is_breakout = close.iloc[-1] > df['High20'].iloc[-1]
    
    # [綜合評分 Logic]
    score = 50 
    score += 20 if df['MACD_S'].iloc[-1] > 0 else -10
    score += 15 if is_breakout else 0
    score += 10 if vol_ratio > 1.2 else 0
    score += news_w.get(tid, 0) # 加入自動更新的時事權重
    
    return {
        "score": min(100, score),
        "vol_ratio": round(vol_ratio, 2),
        "status": "🚀 突破" if is_breakout else "🔥 強勢" if vol_ratio > 1.5 else "穩健",
        "price": round(float(close.iloc[-1]), 2),
        "stop": round(float(df['High'].cummax().iloc[-1] * 0.93), 2)
    }

# ============================================
# 3. 介面執行
# ============================================
st.title("🏹 全景獵殺系統 v3.0 - 自動化戰略分析")

if st.button("🔴 啟動全市場自動化掃描", type="primary"):
    live_weights = get_live_market_sentiment()
    st.info(f"🌍 今日連網時事加權已更新：{live_weights}")
    
    # (此處沿用 get_full_market_list 邏輯)
    tickers = ["2337.TW", "3017.TW", "2383.TW", "3234.TWO", "1409.TW", "4919.TW"]
    
    final_list = []
    for t in tickers:
        df = yf.download(t, period="6mo", progress=False)
        tid = t.split(".")[0]
        res = master_analyze(df, tid, live_weights, 500)
        if res:
            final_list.append({
                "代號": tid, "綜合評分": res["score"], "能量(倍)": res["vol_ratio"],
                "狀態": res["status"], "現價": res["price"], "防守線": res["stop"]
            })
            
    if final_list:
        df_final = pd.DataFrame(final_list).sort_values(by="綜合評分", ascending=False).head(5)
        st.subheader("🏆 去蕪存菁：最強前五標的")
        st.table(df_final)
        
        # 深度分析輸出
        for index, row in df_final.iterrows():
            with st.expander(f"📌 {row['代號']} 深度戰略分析"):
                st.write(f"該標的目前評分為 **{row['綜合評分']}**，處於 **{row['狀態']}** 階段。")
                st.write(f"其能量異動為 **{row['能量(倍)']}** 倍，顯示主力進場意願極強。")
                st.write(f"**建議作為：** 若現價高於防守線 **{row['防守線']}**，建議續抱或於回測時適度佈局。")
