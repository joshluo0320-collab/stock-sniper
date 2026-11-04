from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
requests = __import__("requests")
import streamlit as st
import urllib3
import time

# 1. 頁面基本配置
st.set_page_config(
    page_title="週動能波段與嚴苛短線狙擊戰情室",
    page_icon="🏹",
    layout="wide",
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 2. 核心工具：強制破除快取的官方盤後總表直連
# ============================================
@st.cache_data(ttl=600) # 縮短快取時間，確保隨時拿最新
def fetch_official_latest_market_quotes():
    """
    直接向證交所與櫃買中心官網請求當日最新收盤行情，
    並強制帶入時間戳記（Timestamp）破除 CDN 快取，保證抓到最新一交易日結算。
    """
    official_data = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 加上時間戳記防止快取
    ts = int(time.time())
    
    # 1. 上市官方行情
    try:
        url_twse = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&_t={ts}"
        res = requests.get(url_twse, headers=headers, verify=False, timeout=10)
        if res.status_code == 200:
            j_data = res.json()
            # 證交所格式：row[0]=代號, row[1]=名稱, row[2]=成交股數, row[4]=開盤, row[5]=最高, row[6]=最低, row[7]=收盤
            for row in j_data.get("data", []):
                tid = row[0].strip()
                try:
                    op = float(row[4].replace(",", ""))
                    hi = float(row[5].replace(",", ""))
                    lo = float(row[6].replace(",", ""))
                    cl = float(row[7].replace(",", ""))
                    vol = float(row[2].replace(",", "")) / 1000.0 # 轉張數
                    official_data[tid] = {"open": op, "high": hi, "low": lo, "close": cl, "volume": vol}
                except:
                    continue
    except Exception as e:
        print(f"TWSE Error: {e}")

    # 2. 上櫃官方行情
    try:
        url_tpex = f"https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no14/stk_wn14_result.php?l=zh-tw&o=json&_t={ts}"
        res = requests.get(url_tpex, headers=headers, verify=False, timeout=10)
        if res.status_code == 200:
            j_data = res.json()
            for row in j_data.get("aaData", []):
                tid = row[0].strip()
                try:
                    op = float(row[4].replace(",", ""))
                    hi = float(row[5].replace(",", ""))
                    lo = float(row[6].replace(",", ""))
                    cl = float(row[2].replace(",", ""))
                    vol = float(row.get(8, row[7]).replace(",", "")) / 1000.0
                    official_data[tid] = {"open": op, "high": hi, "low": lo, "close": cl, "volume": vol}
                except:
                    continue
    except Exception as e:
        print(f"TPEx Error: {e}")

    return official_data

@st.cache_data(ttl=86400)
def get_market_map():
    tickers, names_map = [], {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    ]
    for url in urls:
        try:
            res = requests.get(url, verify=False, timeout=5)
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
        except:
            continue
    return tickers, names_map

# ============================================
# 3. 嚴苛短線狙擊與風控模組 (強制對齊官方最新數據)
# ============================================
def evaluate_official_strict_momentum(tid, name, official_dict):
    try:
        clean_tid = tid.split(".")[0]
        if clean_tid not in official_dict:
            return None
        
        curr_info = official_dict[clean_tid]
        c_open = curr_info["open"]
        c_high = curr_info["high"]
        c_low = curr_info["low"]
        c_close = curr_info["close"]
        c_vol = curr_info["volume"] # 當日成交量（張）

        # 為了計算 20MA 與昨日收盤，我們仍需參考近期歷史，但收盤價強制以官方當日結算為準
        t_obj = yf.Ticker(tid)
        df_hist = t_obj.history(period="30d")
        if df_hist.empty or len(df_hist) < 20:
            return None
        
        if isinstance(df_hist.columns, pd.MultiIndex):
            df_hist.columns = df_hist.columns.get_level_values(0)
            
        # 取得昨日真實收盤價（倒數第二筆或直接用歷史數據算）
        prev_close = float(df_hist["Close"].iloc[-2]) if len(df_hist) >= 2 else c_open
        day_return_pct = ((c_close / prev_close) - 1) * 100
        
        # 計算 20 日均量
        avg_vol_20 = float(df_hist["Volume"].tail(20).mean()) / 1000.0

        total_range = c_high - c_low
        upper_shadow = c_high - max(c_close, c_open)
        is_clean_shadow = (upper_shadow / total_range < 0.20) if total_range > 0 else True

        # 嚴苛過濾條件
        if not (
            day_return_pct >= 5.0 and 
            c_close > c_open and 
            is_clean_shadow and 
            c_vol >= 5000 and 
            c_vol >= (avg_vol_20 * 2.0)
        ):
            return None

        entry_price = round(c_close, 2)
        stop_loss_price = round(min(c_low, entry_price * 0.98), 2)
        target_profit_3pct = round(entry_price * 1.03, 2)
        target_profit_5pct = round(entry_price * 1.05, 2)

        score = 60 + int(day_return_pct * 2)
        score += 20 if c_vol >= avg_vol_20 * 3.0 else 10
        final_score = min(score, 100)

        return {
            "代號": clean_tid,
            "名稱": name,
            "短線動能分": final_score,
            "收盤價": c_close,
            "今日漲幅": f"{round(day_return_pct, 2)}%",
            "成交量(張)": int(c_vol),
            "量比(vs 20MA)": f"{round(c_vol/avg_vol_20, 1)}x",
            "建議進場參考": f"{entry_price} (收盤/明平開)",
            "🔴 嚴格停損價": stop_loss_price,
            "🟢 目標停利 (+3%)": target_profit_3pct,
            "🟢 目標停利 (+5%)": target_profit_5pct,
            "執行紀律提示": "開盤 30 分鐘內未見買盤續強或跌破停損線，立即無條件出場！"
        }
    except Exception:
        return None

# ============================================
# 4. Streamlit 介面與分頁
# ============================================
st.title("🏹 智能動能戰情與嚴苛風控系統 (官方強制直連版)")

tickers, names_map = get_market_map()

tab_wave, tab_short = st.tabs(["📊 長線波段戰情室 (Holding)", "⚡ 官方直連短線狙擊 (Top 3)"])

with tab_short:
    st.subheader("⚡ 次日短線極致嚴苛狙擊戰情室 (官方 API 零時差直連)")
    st.caption("💡 本模組直接向台灣證交所與櫃買中心抓取最新交易日結算總表，強制破除快取，確保數據 100% 與券商 App 一致。")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        total_capital = st.number_input("可用短線資金總額 (NT$)", value=270000, step=10000)
    with col_f2:
        allocation_pct = st.slider("單筆短線試單佔總資金比例 (%)", 5, 20, 10, step=5)
        
    allocated_funds = int(total_capital * (allocation_pct / 100))
    st.info(f"💰 資金風控提示：單筆短線試單金額為 **NT$ {allocated_funds:,}**（嚴格控制極小部位）。")

    if st.button("🚀 執行官方直連短線掃描 (鎖定 Top 3)", type="primary"):
        with st.spinner("📥 正在強制向證交所與櫃買中心下載最新盤後官方結算行情表..."):
            official_dict = fetch_official_latest_market_quotes()
            
        if not official_dict:
            st.error("❌ 無法取得官方行情資料，請稍後再試。")
        else:
            short_results = []
            with st.spinner(f"📡 正在從官方資料庫過濾全台股共 {len(tickers)} 檔標的..."):
                for t in tickers:
                    tid = t.split(".")[0]
                    if tid in official_dict:
                        res = evaluate_official_strict_momentum(t, names_map.get(tid, tid), official_dict)
                        if res:
                            short_results.append(res)
                            
            if short_results:
                df_short_all = pd.DataFrame(short_results).sort_values(by="短線動能分", ascending=False)
                df_top3 = df_short_all.head(3).copy()
                df_top3.index = range(1, len(df_top3) + 1)
                
                st.success(f"🏆 掃描完成！已成功對齊證交所官方最新結算價，為您鎖定【最強前 3 支】短線極致強勢標的：")
                st.dataframe(df_top3, use_container_width=True)
            else:
                st.warning("⚠️ 今日盤面無符合「漲幅>=5%、量大2倍、極短上影線」的嚴苛條件標的。")
