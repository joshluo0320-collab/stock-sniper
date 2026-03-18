import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ============================================
# 1. 系統設定
# ============================================
st.set_page_config(page_title="台股決賽輪 - 精選獵殺版", layout="wide")

st.sidebar.header("🕹️ 獵殺控制台")
# 10D 趨勢門檻
min_p10_threshold = st.sidebar.slider("📈 10日趨勢過濾門檻", 10, 95, 40)
trail_percent = st.sidebar.slider("🛡️ 動態止盈回落 (%)", 3.0, 15.0, 7.0)

st.sidebar.markdown("---")
st.sidebar.header("📋 我的庫存建倉")
# 格式：代號,成本 (例如 2337,34)
inventory_input = st.sidebar.text_area("輸入庫存 (代號,成本)", value="2337,34\n1409,16.5")

# ============================================
# 2. 核心計算邏輯
# ============================================
def calculate_logic(df, tp_pct):
    if len(df) < 20: return df
    close = df['Close']
    # 技術指標
    exp12 = close.ewm(span=12, adjust=False).mean()
    exp26 = close.ewm(span=26, adjust=False).mean()
    df['MACD_S'] = (exp12 - exp26).diff() 
    df['Vol_R'] = df['Volume'] / df['Volume'].rolling(5).mean()
    df['High20'] = df['High'].rolling(20).max().shift(1)
    # 動態止盈
    df['Rolling_Peak'] = df['High'].cummax() 
    df['Trailing_Stop_Line'] = df['Rolling_Peak'] * (1 - tp_pct / 100)
    return df

def predict_probabilities(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # 10D 趨勢：結構力
    p10 = 40 + (20 if last['MACD_S'] > 0 else 0) + (15 if last['Vol_R'] > 1.1 else 0) + (20 if last['Close'] > last['High20'] else 0)
    # 5D 噴發：加速度
    p5 = 20 + (40 if last['MACD_S'] > prev['MACD_S'] else 0) + (30 if last['Vol_R'] > 1.5 else 0)
    return min(98, p5), min(98, p10)

# ============================================
# 3. 主介面執行
# ============================================
st.title("🚀 台股決賽輪：精選標的 10D 趨勢監控")

# B 計畫：直接定義精選標的 (避免網頁解析錯誤)
# 你可以在這裡隨時增加你想關注的代號
focus_list = {
    "2337.TW": "旺宏", "1409.TW": "新纖", "3234.TW": "光環", 
    "4164.TW": "承業醫", "2330.TW": "台積電", "2454.TW": "聯發科",
    "6443.TW": "元晶", "3037.TW": "欣興", "2368.TW": "金像電"
}

if st.button("🔴 啟動精選標的獵殺分析", type="primary"):
    all_results = []
    bar = st.progress(0)
    
    tickers = list(focus_list.keys())
    for i, t in enumerate(tickers):
        bar.progress((i + 1) / len(tickers))
        try:
            df = yf.download(t, period="4mo", progress=False)
            if df.empty or len(df) < 20: continue
            
            # 修復 yfinance MultiIndex 問題
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df = calculate_logic(df.dropna(), trail_percent)
            p5, p10 = predict_probabilities(df)
            
            if p10 >= min_p10_threshold:
                last_p = df['Close'].iloc[-1]
                all_results.append({
                    "代號": t.replace(".TW",""),
                    "名稱": focus_list[t],
                    "10D趨勢分": f"{int(p10)}%",
                    "5D噴發分": f"{int(p5)}%",
                    "現價": round(float(last_p), 2),
                    "建議進場價": round(float(last_p) * 1.005, 2),
                    "動態止盈線": round(df['Trailing_Stop_Line'].iloc[-1], 2),
                    "狀態": "🔥 極強" if p5 > 65 else "📈 穩健"
                })
        except: continue
    
    bar.empty()
    if all_results:
        st.subheader(f"🏆 符合 {min_p10_threshold}% 10D 門檻之標的")
        st.dataframe(pd.DataFrame(all_results).sort_values(by="10D趨勢分", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning("精選標的中暫無符合門檻者。")

st.markdown("---")

# --- 庫存回測區 ---
st.subheader("💰 庫存盈利與動態撤退監控")
if st.button("📊 執行庫存盈虧報告"):
    inv_results = []
    for item in inventory_input.split('\n'):
        if ',' in item:
            try:
                tid, cost = item.split(',')
                t = f"{tid.strip()}.TW"
                df_inv = yf.download(t, period="2y", progress=False)
                if not df_inv.empty:
                    if isinstance(df_inv.columns, pd.MultiIndex): df_inv = df_inv.droplevel(1, axis=1)
                    df_inv = calculate_logic(df_inv, trail_percent)
                    last_p = df_inv['Close'].iloc[-1]
                    stop_line = df_inv['Trailing_Stop_Line'].iloc[-1]
                    inv_results.append({
                        "代號": tid, "成本": float(cost), "現價": round(last_p, 2),
                        "累積盈利": f"{round((last_p/float(cost)-1)*100, 2)}%",
                        "動態止盈線": round(stop_line, 2),
                        "狀態": "⚠️ 建議撤退" if last_p < stop_line else "✅ 獲利中"
                    })
            except: continue
    if inv_results: st.table(pd.DataFrame(inv_results))
