import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ==========================================
# 1. 系統設定 & 全自動掃描清單
# ==========================================
st.set_page_config(page_title="股市全自動掃描", page_icon="📡", layout="wide")

# 📋 內建自動掃描清單 (模擬全市場熱門股掃描)
# 由於 yfinance 逐檔掃描 1007 檔需時過久，這裡內建「台股成交量活絡 150 強」
AUTO_SCAN_LIST = [
    # 權值與半導體
    "2330", "2317", "2454", "2303", "2308", "3711", "3034", "3035", "2379", "3443", 
    "2344", "2408", "3008", "3044", "2363", "2337", "4961", "4967", "6415", "6753",
    # AI 伺服器 & 電腦
    "3231", "2382", "2356", "6669", "2301", "3017", "2376", "3013", "2324", "2357",
    "2377", "2395", "2421", "2423", "2449", "2486", "3019", "3046", "3515", "3706",
    # 航運
    "2603", "2609", "2615", "2618", "2610", "2605", "2606", "2637", "5608", "2601",
    # 重電與綠能
    "1513", "1519", "1503", "1504", "1609", "6806", "1514", "1522", "1605", "1612",
    # 金融
    "2881", "2882", "2891", "2886", "2884", "2892", "2885", "2880", "2883", "2887",
    "2890", "5880", "2801", "2834",
    # PCB & 網通
    "3037", "8046", "2368", "2313", "5388", "6213", "6278", "2345", "3704", "8021",
    # 光學 & 面板
    "3008", "3406", "2409", "3481", "6116", "3019", "3504",
    # 傳產與其他熱門
    "1101", "1102", "1216", "1301", "1303", "1326", "1402", "1476", "2002", "2014",
    "2027", "2049", "2105", "2201", "2204", "2501", "2542", "2614", "2912", "9904",
    "9910", "9945", "4916", "9958", "4763", "1722", "1708", "4125", "1795"
]

# 中文名稱對照 (輔助用，主要抓取系統名稱)
TW_STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2337": "旺宏", 
    "4916": "事欣科", "8021": "尖點", "2603": "長榮", "3231": "緯創"
}

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000},
        {"code": "8021", "name": "尖點", "cost": 239.0, "shares": 200}
    ]

if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 2. 核心運算引擎 (歷史勝率回測)
# ==========================================
def generate_strategy_advice(profit_pct):
    if profit_pct >= 10: return "🚀 獲利拉開，移動停利！"
    elif 5 <= profit_pct < 10: return "📈 表現不錯，續抱觀察。"
    elif 0 <= profit_pct < 5: return "🛡️ 成本保衛，密切觀察。"
    elif -5 < profit_pct < 0: return "⚠️ 小幅虧損，檢查支撐。"
    else: return "🛑 虧損擴大，嚴禁凹單！"

def get_stock_name(code, info):
    if code in TW_STOCK_NAMES: return TW_STOCK_NAMES[code]
    try:
        name = info.get('longName') or info.get('shortName')
        if name: return name
    except: pass
    return code

def calculate_win_rate(df, days, target_pct):
    """計算 N 日勝率"""
    if len(df) < days + 1: return 0
    # 未來報酬率計算
    future_close = df['Close'].shift(-days) 
    returns = (future_close - df['Close']) / df['Close'] * 100
    
    wins = (returns >= target_pct).sum()
    total_valid = returns.count()
    if total_valid == 0: return 0
    return (wins / total_valid) * 100

def calculate_sniper_score(data_dict):
    """戰術評分計算 (加重勝率權重)"""
    score = 60 
    
    # 1. 乖離
    bias_str = data_dict['乖離']
    if "🟢 安全" in bias_str: score += 10
    elif "⚪ 合理" in bias_str: score += 5
    elif "🟠 略貴" in bias_str: score -= 5
    elif "🔴 危險" in bias_str: score -= 15
    
    # 2. KD
    kd_str = data_dict['KD']
    if "🔥 續攻" in kd_str: score += 10
    elif "⚪ 整理" in kd_str: score += 0
    elif "🧊 超賣" in kd_str: score += 5 
    elif "⚠️ 過熱" in kd_str: score -= 5
    
    # 3. MACD
    macd_str = data_dict['MACD']
    if "⛽ 滿油" in macd_str: score += 15
    elif "🚗 加速" in macd_str: score += 10
    elif "🛑 減速" in macd_str: score -= 10
    
    # 4. 歷史勝率 (5日)
    win_5d = data_dict['5日勝率%']
    if win_5d > 50: score += 20
    elif win_5d > 30: score += 10
    elif win_5d < 10: score -= 10
    
    return max(0, min(100, score))

def get_dashboard_data(ticker_code, min_vol, target_rise):
    code = str(ticker_code)
    full_ticker = f"{code}.TW" if not code.endswith(('.TW', '.TWO')) else code
    try:
        stock = yf.Ticker(full_ticker)
        # 抓 1 年資料算勝率
        df = stock.history(period="1y") 
        if df.empty or len(df) < 60: return None
        
        # 濾網：成交量 (張)
        last_vol = df['Volume'].iloc[-1]
        if last_vol < min_vol * 1000: return None

        stock_name = get_stock_name(code, stock.info)
        close = df['Close']
        last_price = close.iloc[-1]
        
        # 指標運算
        ma20 = close.rolling(20).mean()
        bias = ((close - ma20) / ma20) * 100
        curr_bias = bias.iloc[-1]
        stop_loss_price = ma20.iloc[-1]
        
        if curr_bias > 10: bias_txt = "🔴 危險"
        elif curr_bias > 5: bias_txt = "🟠 略貴"
        elif curr_bias < -5: bias_txt = "🟢 安全"
        else: bias_txt = "⚪ 合理"
        
        high60 = df['High'].rolling(60).max()
        low60 = df['Low'].rolling(60).min()
        pos = ((close - low60) / (high60 - low60)) * 100
        
        rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean()
        d = k.ewm(com=2).mean()
        curr_k = k.iloc[-1]
        
        if curr_k > 80: kd_txt = "⚠️ 過熱"
        elif curr_k > d.iloc[-1]: kd_txt = "🔥 續攻"
        elif curr_k < 20: kd_txt = "🧊 超賣"
        else: kd_txt = "⚪ 整理"
        
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26
        macd = dif.ewm(span=9).mean()
        osc = dif - macd
        curr_osc = osc.iloc[-1]
        
        if curr_osc > 0 and curr_osc > osc.iloc[-2]: macd_txt = "⛽ 滿油"
        elif curr_osc > 0: macd_txt = "🚗 加速"
        elif curr_osc < 0 and curr_osc > osc.iloc[-2]: macd_txt = "🔧 收腳"
        else: macd_txt = "🛑 減速"

        # 勝率
        win_rate_5d = calculate_win_rate(df, 5, target_rise)
        win_rate_10d = calculate_win_rate(df, 10, target_rise)

        return {
            "選取": True,
            "代號": code,
            "名稱": stock_name,
            "收盤價": last_price,
            "停損價": stop_loss_price,
            "乖離": bias_txt,
            "KD": kd_txt,
            "MACD": macd_txt,
            "位階%": pos.iloc[-1],
            "5日勝率%": win_rate_5d,
            "10日勝率%": win_rate_10d,
            "連結": f"https://tw.stock.yahoo.com/quote/{code}"
        }
    except: return None

# ==========================================
# 3. 頁面功能模組
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板")
    if st.button("🔄 刷新"): st.rerun()

    cols = st.columns(3)
    for i, stock in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{stock['code']}.TW")
                h = t.history(period="5d")
                if not h.empty:
                    last = h.iloc[-1]
                    prev = h.iloc[-2]['Close']
                    price = last['Close']
                    chg = price - prev
                    pct = chg/prev*100
                    profit = (price * stock['shares']) - (stock['cost'] * stock['shares'])
                    prof_pct = profit / (stock['cost'] * stock['shares']) * 100
                    
                    with st.container(border=True):
                        st.subheader(f"{stock['name']} ({stock['code']})")
                        st.metric("現價", f"{price:.2f}", f"{chg:.2f} ({pct:.2f}%)")
                        color = ":red" if profit > 0 else ":green"
                        st.markdown(f"損益： {color}[{int(profit):,} ({prof_pct:.1f}%)]")
                        st.divider()
                        st.markdown(f"💡 {generate_strategy_advice(prof_pct)}")
            except:
                st.error(f"{stock['name']} 讀取錯誤")

def page_scanner():
    st.header("🎯 全市場自動掃描")
    
    # 左側控制台 (參數設定)
    with st.sidebar:
        st.header("⚙️ 掃描參數")
        st.caption("調整條件以過濾雜訊")
        
        # 成交量濾網
        min_vol = st.number_input("🌊 最低成交量 (張)", min_value=0, value=1000, step=100, help="過濾掉流動性太差的股票")
        
        # 漲幅拉桿 (計算勝率用)
        target_rise = st.slider("🎯 目標漲幅 (%)", min_value=1, max_value=20, value=3, format="%d%%")
        st.info(f"勝率定義：買進持有後，獲利 > {target_rise}% 的歷史機率")

    # 隱藏的自動掃描清單 (不顯示輸入框)
    target_list = list(set(AUTO_SCAN_LIST)) # 使用內建清單

    if st.button("🚀 啟動全自動掃描 (Auto Scan)"):
        st.write(f"正在連線掃描市場熱門股 ({len(target_list)} 檔)，請稍候...")
        
        res = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, c in enumerate(target_list):
            status.text(f"掃描中：{c} ...")
            bar.progress((i+1)/len(target_list))
            d = get_dashboard_data(c, min_vol, target_rise)
            if d: res.append(d)
        
        bar.empty()
        status.empty()
        
        if res:
            st.session_state.scan_results = pd.DataFrame(res)
        else:
            st.warning("無符合條件的股票 (請嘗試降低成交量門檻)")

    # 結果顯示
    if st.session_state.scan_results is not None:
        st.subheader("2. 戰隊篩選")
        st.caption("在此處取消勾選「暫不考慮」的股票。")
        
        edited_df = st.data_editor(
            st.session_state.scan_results,
            column_config={
                "選取": st.column_config.CheckboxColumn("加入戰隊?", default=True),
                "收盤價": st.column_config.NumberColumn(format="$%.2f"),
                "位階%": st.column_config.ProgressColumn("位階%", format="%.0f%%", min_value=0, max_value=100),
                "5日勝率%": st.column_config.ProgressColumn(f"5日賺{target_rise}%機率", format="%.1f%%", min_value=0, max_value=100),
                "10日勝率%": st.column_config.ProgressColumn(f"10日賺{target_rise}%機率", format="%.1f%%", min_value=0, max_value=100),
                "連結": st.column_config.LinkColumn("情報"),
                "停損價": None
            },
            disabled=["代號", "名稱", "收盤價", "乖離", "KD", "MACD", "位階%", "5日勝率%", "10日勝率%"],
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        
        if st.button("🏆 開始評測 (計算 AI 分數)"):
            final_df = edited_df[edited_df["選取"] == True].copy()
            
            if not final_df.empty:
                # 計算分數
