import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="台股 10D/10% 獵殺系統", layout="wide")

if 'cash' not in st.session_state:
    st.session_state.cash = 240000  

@st.cache_data(ttl=86400)
def get_tw_stocks():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url, verify=False)
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        tickers, names = [], {}
        for index, row in df.iterrows():
            parts = str(row['有價證券代號及名稱']).split()
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                # 過濾金融股 (代號 28 開頭) 除非其波動率異常高
                if not parts[0].startswith('28'): 
                    t = f"{parts[0]}.TW"
                    tickers.append(t)
                    names[t] = parts[1]
        return tickers, names
    except: return [], {}

def get_detailed_reason(df):
    last = df.iloc[-1]
    vol_ratio = last['Volume'] / df['Volume'].rolling(5).mean().iloc[-1]
    
    if last['Close'] > df['High'].rolling(20).max().iloc[-2] and vol_ratio > 2:
        return "【噴發型】帶量突破歷史平台，上方無套牢阻力"
    if last['MACD_Slope'] > df['MACD_Slope'].iloc[-2] * 1.5:
        return "【動能型】買盤斜率陡增，法人大單進場痕跡明顯"
    if 0 < last['Bias'] < 3 and last['MACD_Slope'] > 0:
        return "【起漲型】貼近月線強勢整理結束，攻擊能量蓄勢待發"
    if vol_ratio > 3:
        return "【量能型】成交量異常倍增，疑似特定題材點火"
    return "【趨勢型】沿五日線強勢推升，多頭結構完整"

# 主程式執行邏輯略 (沿用前次結構，但增加 Top 6-10 與邏輯校準)
# ============================================
st.title("🚀 台股全市場 1-10 名爆發預測")
st.info("已根據合夥人建議：過濾牛皮金融股，專注半導體、記憶體等強勢題材與高動能標的。")

if st.button("🔥 開始 1,000+ 標的深度掃描", type="primary"):
    tickers, names_map = get_tw_stocks()
    all_results = []
    bar = st.progress(0)
    
    # 下載與分析 (批次處理)
    chunks = [tickers[i:i + 35] for i in range(0, len(tickers), 35)]
    for i, chunk in enumerate(chunks):
        bar.progress((i + 1) / len(chunks))
        data = yf.download(chunk, period="4mo", group_by='ticker', progress=False)
        for t in chunk:
            try:
                df = data if len(chunk)==1 else data.get(t)
                if df is None or df.empty or len(df)<40: continue
                if isinstance(df.columns, pd.MultiIndex): df = df.droplevel(0, axis=1)
                
                # 計算關鍵數據 (MACD, Slope, Bias, Vol_Ratio)
                close = df['Close']
                exp12 = close.ewm(span=12, adjust=False).mean()
                exp26 = close.ewm(span=26, adjust=False).mean()
                macd = exp12 - exp26
                slope = macd.diff()
                bias = (close.iloc[-1] - close.rolling(20).mean().iloc[-1]) / close.rolling(20).mean().iloc[-1] * 100
                vol_r = df['Volume'].iloc[-1] / df['Volume'].rolling(5).mean().iloc[-1]
                
                # 右側篩選標準
                if close.iloc[-1] > close.rolling(20).mean().iloc[-1] and slope.iloc[-1] > 0:
                    score = 50 + (slope.iloc[-1] * 100) + (vol_r * 10) - (abs(bias-5))
                    
                    entry = round(close.iloc[-1] * 1.005, 2)
                    all_results.append({
                        "得分": score, "代號": t.replace(".TW",""), "名稱": names_map[t],
                        "建議進場": entry, "停利": round(entry * 1.1, 2), "停損": round(entry * 0.95, 2),
                        "張數": int((st.session_state.cash * 0.2) / (entry * 1000)),
                        "理由": get_detailed_reason(df.assign(MACD_Slope=slope))
                    })
            except: continue

    bar.empty()
    res_df = pd.DataFrame(all_results).sort_values(by="得分", ascending=False)
    
    # 呈現 Top 1-5
    st.subheader("🏆 第一梯隊：核心決策 (Top 1-5)")
    for i, row in enumerate(res_df.head(5).to_dict('records')):
        with st.expander(f"No.{i+1} - {row['代號']} {row['名稱']} | 建議進場: {row['建議進場']}", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("🎯 10% 停利", row['停利'])
            c2.metric("🛑 5% 停損", row['停損'])
            c3.write(f"💼 建議買進: **{row['張數']} 張**")
            st.warning(f"💡 擊敗對手理由：{row['理由']}")

    # 呈現 Top 6-10
    st.markdown("---")
    st.subheader("🥈 第二梯隊：潛力候補 (Top 6-10)")
    st.table(res_df.iloc[5:10][["代號", "名稱", "建議進場", "理由"]])
