import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import urllib3
import os
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 證交所全上市個股名單動態爬取
# ============================================
@st.cache_data(ttl=86400)
def get_all_tw_stocks():
    try:
        url = "http://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = pd.read_html(url)[0]
        res.columns = res.iloc[0]
        res = res.iloc[1:]
        res = res[res['CFICode'] == 'ESVUTFR']  # 嚴格鎖定上市普通股
        
        tickers = []
        names_map = {}
        for item in res['有價證券代號及名稱']:
            try:
                parts = item.split('\u3000')
                if len(parts) == 2 and len(parts[0]) == 4:
                    ticker_tw = f"{parts[0]}.TW"
                    tickers.append(ticker_tw)
                    names_map[ticker_tw] = parts[1]
            except:
                continue
        return tickers, names_map
    except Exception as e:
        st.error(f"❌ 證交所名單連線失敗: {str(e)}")
        # 基礎防呆保留
        return ["2317.TW", "2330.TW", "2352.TW", "3017.TW"], {"2317.TW":"鴻海", "2330.TW":"台積電", "2352.TW":"佳世達", "3017.TW":"奇鋐"}

# ============================================
# 2. 核心戰略計分與濾網
# ============================================
def calculate_radar_score(df, tid, name, min_p, max_p):
    try:
        # 排除無效數據
        if df.empty or len(df) < 35: 
            return {"Error": "數據長度不足"}
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
            
        df = df.dropna(subset=['Close', 'High', 'Low'])
        last_p = round(float(df['Close'].iloc[-1]), 1)
        
        # 價格區間過濾
        if not (min_p <= last_p <= max_p): 
            return {"Error": f"股價 {last_p} 不在區間內"}
            
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma10 = df['Close'].rolling(10).mean().iloc[-1]
        
        # 1. 氣勢分析 (MACD斜率)
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_slope = (ema12 - ema26).diff().iloc[-1]
        momentum_text = "🏎️ 全油門衝刺" if macd_slope > 0 else "🐢 動能減速"
        
        # 2. 路況分析 (10MA 乖離過濾)
        bias_10 = round(((last_p / ma10) - 1) * 100, 1)
        if last_p > ma10 * 1.08:
            road_text = "🚨 嚴重超速(不追)"
        else:
            road_text = "🗺️ 前方無障礙" if last_p > ma5 else "⚠️ 路面顛簸"
            
        # 3. 能量分析 (ATR)
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr_ratio = round((tr.rolling(14).mean().iloc[-1] / last_p) * 100, 1)
        energy_text = "⛽ 油量正常" if atr_ratio >= 1.5 else "🪫 缺乏波動"
        
        is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
        
        score = int(((50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
        if score < 0: score = 0
        if score > 100: score = 100
        
        return {
            "代號": tid.split(".")[0],
            "股票名稱": name,
            "綜合勝率": f"{score}%",
            "↑氣勢分析": momentum_text,
            "路況分析": road_text,
            "能量分析": energy_text,
            "今日收盤": last_p,
            "明日建議進場區": f"{round(last_p*0.99, 1)} ~ {round(last_p*1.01, 1)}",
            "raw_score": score,
            "Status": "通過"
        }
    except Exception as e:
        return {"Error": f"計算異常: {str(e)}"}

# 單股獨立數據流對接
def fetch_stock_data(ticker, name, min_p, max_p):
    try:
        # 僅下載最短所需天數，減少被 Yahoo 阻斷的機率
        df = yf.Ticker(ticker).history(period="40d", progress=False)
        return calculate_radar_score(df, ticker, name, min_p, max_p)
    except:
        return {"Error": "Yahoo 連線中斷"}

# ============================================
# 3. Streamlit UI 介面
# ============================================
st.set_page_config(page_title="v23.3 選股實驗室", layout="wide")
st.title("🏹 v23.3 策略雷達看板 (純自動選股版)")

st.sidebar.header("🕹️ 戰略參數控制台")
target_win = st.sidebar.slider("🎯 買入勝率門檻 (%)", 50, 100, 60, step=5)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 股價自選區間")
min_p_input = st.sidebar.number_input("最低股價 (元)", min_value=1.0, value=10.0, step=5.0)
max_p_input = st.sidebar.number_input("最高股價 (元)", min_value=1.0, value=150.0, step=5.0)

# 點擊按鈕啟動純選股掃描
if st.button("🔴 啟動全台股 1,000+ 支標的之地毯式獵殺", type="primary"):
    with st.status("正在下載全市場歷史數據...", expanded=True) as status:
        
        tickers, names_map = get_all_tw_stocks()
        st.write(f"🌐 成功自台灣證交所取得 {len(tickers)} 檔上市普通股名單。")
        st.write("⏳ 開始執行背景併發下載與戰略指標解析...")
        
        radar_results = []
        error_count = 0
        filtered_count = 0
        
        # 線程池平行處理
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            future_to_ticker = {
                executor.submit(fetch_stock_data, tk, names_map[tk], min_p_input, max_p_input): tk 
                for tk in tickers
            }
            for future in concurrent.futures.as_completed(future_to_ticker):
                res = future.result()
                if res:
                    if "Error" in res:
                        error_count += 1
                        # 僅在背景累計錯誤，不讓畫面上傳錯誤訊息洗版
                    elif res.get("Status") == "通過":
                        radar_results.append(res)
                        
        status.update(label=f"🎯 掃描完成。成功獲取並解析個股共 {len(radar_results)} 支標的。", state="complete")
        
        # --- 渲染圖 2 戰略看板 ---
        st.markdown("---")
        st.success(f"📊 報告：全市場在股價區間內（{min_p_input}~{max_p_input}元）共獲取符合條件標的。")
        
        if radar_results:
            full_radar_df = pd.DataFrame(radar_results)
            # 依據分數排序，篩選大於勝率門檻，且路況健康的標的
            final_df = full_radar_df[
                (full_radar_df["raw_score"] >= target_win) & 
                (full_radar_df["路況分析"] == "🗺️ 前方無障礙")
            ]
            
            if not final_df.empty:
                st.write(f"### 📈 符合門檻之黃金候選名單（門檻：{target_win}%）")
                st.dataframe(
                    final_df[["股票名稱", "代號", "綜合勝率", "↑氣勢分析", "路況分析", "能量分析", "今日收盤", "明日建議進場區"]].sort_values(by="綜合勝率", ascending=False),
                    use_container_width=True, 
                    hide_index=True
                )
            else:
                st.info(f"💡 今日有成功下載到數據，但無任何個股達到您設定的 {target_win}% 勝率門檻且路況無障礙。")
        else:
            st.error("❌ 警告：所有個股回傳數據均為空值，或被股價區間濾網全數過濾。請確認下方區間設定，或嘗試放寬最低/最高股價限制。")
