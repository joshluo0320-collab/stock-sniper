import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. SSL 憑證修復 (必要)
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# ==========================================
# 1. 系統設定 & 自動抓取全市場清單
# ==========================================
st.set_page_config(page_title="全市場高精準掃描", page_icon="🎯", layout="wide")

@st.cache_data(ttl=3600*24)
def get_all_tw_stocks():
    """自動聯網抓取台股上市普通股代號"""
    stock_list = []
    try:
        url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        response = requests.get(url_twse, headers=HEADERS, verify=False)
        response.encoding = 'big5'
        df_twse = pd.read_html(StringIO(response.text))[0]
        df_twse.columns = df_twse.iloc[0]
        df_twse = df_twse.iloc[1:]
        df_twse = df_twse[df_twse['CFICode'] == 'ESVUFR']
        
        for item in df_twse['有價證券代號及名稱']:
            code, name = item.split('\u3000')
            if len(code) == 4:
                stock_list.append(code)
    except Exception as e:
        st.error(f"連線失敗，啟用備援清單。錯誤: {e}")
        return ["2330", "2317", "2454", "2303", "2603", "2609", "2615", "3231", "2382", "4916", "8021", "2337"]
    return list(set(stock_list))

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
# 2. 核心運算引擎 (新增 RSI 與 趨勢判斷)
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
    if len(df) < days + 1: return 0
    future_close = df['Close'].shift(-days) 
    returns = (future_close - df['Close']) / df['Close'] * 100
    wins = (returns >= target_pct).sum()
    total_valid = returns.count()
    if total_valid == 0: return 0
    return (wins / total_valid) * 100

def calculate_rsi(series, period=14):
    """計算 RSI 指標"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_sniper_score(data_dict):
    score = 60 
    
    # 1. 乖離率
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
    
    # 4. RSI (新增精準度變項)
    rsi_val = data_dict['RSI']
    if 40 <= rsi_val <= 70: score += 10 # 健康區間
    elif rsi_val > 80: score -= 10 # 過熱風險
    elif rsi_val < 20: score += 5 # 反彈機會
    
    # 5. 歷史勝率
    win_5d = data_dict['5日勝率%']
    if win_5d > 50: score += 20
    elif win_5d > 30: score += 10
    elif win_5d < 10: score -= 10
    
    return max(0, min(100, score))

def get_dashboard_data(ticker_code, min_vol, target_rise, ma_filter):
    code = str(ticker_code)
    full_ticker = f"{code}.TW" if not code.endswith(('.TW', '.TWO')) else code
    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="1y") 
        if df.empty or len(df) < 60: return None
        
        # 成交量濾網
        last_vol = df['Volume'].iloc[-1]
        if last_vol < min_vol * 1000: return None

        stock_name = get_stock_name(code, stock.info)
        close = df['Close']
        last_price = close.iloc[-1]
        
        # 均線計算
        ma20 = close.rolling(20).mean()
        stop_loss_price = ma20.iloc[-1]
        
        # --- 新增：趨勢濾網 (Trend Filter) ---
        # 如果開啟濾網，且股價 < 月線，直接淘汰
        if ma_filter and last_price < stop_loss_price:
            return None

        # 乖離率
        bias = ((close - ma20) / ma20) * 100
        curr_bias = bias.iloc[-1]
        
        if curr_bias > 10: bias_txt = "🔴 危險"
        elif curr_bias > 5: bias_txt = "🟠 略貴"
        elif curr_bias < -5: bias_txt = "🟢 安全"
        else: bias_txt = "⚪ 合理"
        
        # RSI 計算 (新增)
        rsi_series = calculate_rsi(close)
        curr_rsi = rsi_series.iloc[-1]
        
        # 位階
        high60 = df['High'].rolling(60).max()
        low60 = df['Low'].rolling(60).min()
        pos = ((close - low60) / (high60 - low60)) * 100
        
        # KD
        rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean()
        d = k.ewm(com=2).mean()
        curr_k = k.iloc[-1]
        
        if curr_k > 80: kd_txt = "⚠️ 過熱"
        elif curr_k > d.iloc[-1]: kd_txt = "🔥 續攻"
        elif curr_k < 20: kd_txt = "🧊 超賣"
        else: kd_txt = "⚪ 整理"
        
        # MACD
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
            "RSI": curr_rsi, # 新增數據
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
    
    # 自動獲取清單
    with st.spinner("📡 正在聯網更新台股清單..."):
        all_stocks = get_all_tw_stocks()
    
    # --- 左側戰情控制台 (Sidebar) ---
    with st.sidebar:
        st.header("⚙️ 戰術控制台")
        st.info(f"📊 市場總股數：{len(all_stocks)} 檔")
        
        st.divider()
        st.subheader("1. 基礎濾網")
        # 成交量
        min_vol = st.number_input("🌊 最低成交量 (張)", min_value=0, value=2000, step=100)
        
        st.subheader("2. 歷史回測設定")
        # 漲幅拉桿
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 20, 3, format="%d%%", help="計算勝率用：過去一年持有N天賺超過此%數的機率")
        
        st.subheader("3. 高精準度濾網 (新增)")
        # 趨勢濾網開關
        ma_filter = st.checkbox("🛡️ 僅顯示多頭排列 (股價 > 月線)", value=False, help="勾選後，將自動過濾掉股價跌破月線的弱勢股，提高勝率。")
        
        st.divider()
        st.caption("設定完成後，請按主畫面按鈕開始掃描")

    # 主畫面掃描區
    if st.button("🚀 啟動全市場掃描", type="primary"):
        st.warning("🛑 掃描進行中... 如需停止，請按瀏覽器右上角的 'Stop' 或 'X'。")
        
        current_res = []
        bar = st.progress(0)
        status = st.empty()
        table_placeholder = st.empty()
        
        for i, c in enumerate(all_stocks):
            status.text(f"分析中 ({i+1}/{len(all_stocks)})：{c} ...")
            bar.progress((i+1)/len(all_stocks))
            
            # 傳入 ma_filter 參數
            d = get_dashboard_data(c, min_vol, target_rise, ma_filter)
            
            if d:
                current_res.append(d)
                # 即時更新顯示
                temp_df = pd.DataFrame(current_res)
                st.session_state.scan_results = temp_df
                # 簡易預覽
                table_placeholder.dataframe(
                    temp_df[["代號", "名稱", "收盤價", "5日勝率%", "乖離"]].tail(3),
                    hide_index=True
                )

        bar.empty()
        status.text(f"掃描完成！共找到 {len(current_res)} 檔。")

    # 結果顯示區
    if st.session_state.scan_results is not None:
        st.subheader("2. 戰隊篩選")
        
        edited_df = st.data_editor(
            st.session_state.scan_results,
            column_config={
                "選取": st.column_config.CheckboxColumn("加入戰隊?", default=True),
                "收盤價": st.column_config.NumberColumn(format="$%.2f"),
                "RSI": st.column_config.NumberColumn("RSI (14)", format="%.1f"), # 新增 RSI 顯示
                "位階%": st.column_config.ProgressColumn("位階%", format="%.0f%%", min_value=0, max_value=100),
                "5日勝率%": st.column_config.ProgressColumn(f"5日勝率 (>{target_rise}%)", format="%.1f%%", min_value=0, max_value=100),
                "10日勝率%": st.column_config.ProgressColumn(f"10日勝率 (>{target_rise}%)", format="%.1f%%", min_value=0, max_value=100),
                "連結": st.column_config.LinkColumn("情報"),
                "停損價": None
            },
            disabled=["代號", "名稱", "收盤價", "RSI", "乖離", "KD", "MACD", "位階%", "5日勝率%", "10日勝率%"],
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        
        if st.button("🏆 開始評測"):
            final_df = edited_df[edited_df["選取"] == True].copy()
            
            if not final_df.empty:
                final_df["戰術評分"] = final_df.apply(lambda row: calculate_sniper_score(row), axis=1)
                final_df = final_df.sort_values(by="戰術評分", ascending=False)
                
                st.subheader("🥇 戰術評測前三名")
                
                top_3 = final_df.head(3)
                top_cols = st.columns(3)
                
                for i, (index, row) in enumerate(top_3.iterrows()):
                    with top_cols[i]:
                        with st.container(border=True):
                            rank_icon = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
                            st.markdown(f"### {rank_icon} 第 {i+1} 名")
                            st.markdown(f"**{row['名稱']} ({row['代號']})**")
                            st.progress(int(row['戰術評分']), text=f"AI 評分: {int(row['戰術評分'])} 分")
                            st.divider()
                            
                            c1, c2 = st.columns(2)
                            c1.metric("🎯 建議進場", f"{row['收盤價']:.2f}")
                            c2.metric("🛡️ 停損 (月線)", f"{row['停損價']:.2f}")
                            
                            if row['收盤價'] < row['停損價']:
                                st.warning("⚠️ 已破月線，觀望")
                            
                            st.caption(f"📊 5日勝率: **{row['5日勝率%']:.1f}%** | RSI: **{row['RSI']:.1f}**")

                st.markdown("---")
                st.subheader("📋 完整評測報告")
                st.dataframe(
                    final_df[["名稱", "代號", "收盤價", "戰術評分", "5日勝率%", "RSI", "乖離", "KD", "MACD"]],
                    column_config={
                        "戰術評分": st.column_config.ProgressColumn("評分", format="%d 分", min_value=0, max_value=100),
                        "5日勝率%": st.column_config.NumberColumn(format="%.1f%%"),
                        "RSI": st.column_config.NumberColumn(format="%.1f"),
                        "收盤價": st.column_config.NumberColumn(format="$%.2f")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.error("您沒有選取任何股票！")

def page_management():
    st.header("➕ 庫存管理")
    with st.form("add"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("代號")
        name = c2.text_input("名稱")
        shares = c3.number_input("股數", value=1000)
        cost = st.number_input("成本", value=100.0)
        if st.form_submit_button("新增"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares})
            st.success("已新增")
            
    if st.session_state.portfolio:
        st.dataframe(pd.DataFrame(st.session_state.portfolio))
        d_idx = st.number_input("刪除索引", min_value=0, max_value=len(st.session_state.portfolio)-1, step=1)
        if st.button("🗑️ 刪除"):
            st.session_state.portfolio.pop(d_idx)
            st.rerun()

def main():
    st.sidebar.title("🦅 戰情室")
    page = st.sidebar.radio("導航", ["📡 全市場掃描", "📊 庫存戰術看板", "➕ 庫存管理"])
    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "📡 全市場掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__":
    main()
