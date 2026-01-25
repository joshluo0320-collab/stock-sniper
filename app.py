import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(page_title="Josh 的股市戰情室", page_icon="🦅", layout="wide")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000},
        {"code": "8021", "name": "尖點", "cost": 239.0, "shares": 200}
    ]

# ==========================================
# 2. 核心運算引擎
# ==========================================
def generate_strategy_advice(profit_pct):
    """(庫存看板用) 生成戰術建議文字"""
    if profit_pct >= 10: return "🚀 **大獲全勝**：獲利拉開，移動停利設好，讓獲利奔跑！"
    elif 5 <= profit_pct < 10: return "📈 **穩健獲利**：表現不錯，續抱觀察。"
    elif 0 <= profit_pct < 5: return "🛡️ **成本保衛**：密切觀察，跌破成本需警戒。"
    elif -5 < profit_pct < 0: return "⚠️ **警戒狀態**：小幅虧損，檢查支撐。"
    else: return "🛑 **停損評估**：虧損擴大，嚴禁凹單！"

def get_smart_stock_data(ticker_code):
    """(庫存看板用) 簡單報價"""
    code = str(ticker_code)
    full_ticker = f"{code}.TW" if not code.endswith(('.TW', '.TWO')) else code
    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="5d")
        if df.empty: return None
        last = df.iloc[-1]
        prev = df.iloc[-2]['Close'] if len(df) >= 2 else last['Close']
        return {
            "code": code,
            "price": last['Close'],
            "change": last['Close'] - prev,
            "pct_change": (last['Close'] - prev) / prev * 100,
            "date": df.index[-1].strftime('%Y-%m-%d'),
            "valid": True
        }
    except: return None

def get_dashboard_data(ticker_code):
    """(選股掃描用) 進階指標運算"""
    code = str(ticker_code)
    full_ticker = f"{code}.TW" if not code.endswith(('.TW', '.TWO')) else code
    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="6mo")
        if df.empty or len(df) < 20: return None
        
        # 1. 基礎數據
        close = df['Close']
        last_price = close.iloc[-1]
        
        # 2. 乖離率 (Bias20)
        ma20 = close.rolling(20).mean()
        bias = ((close - ma20) / ma20) * 100
        
        # 3. 位階 (Position)
        high60 = df['High'].rolling(60).max()
        low60 = df['Low'].rolling(60).min()
        pos = ((close - low60) / (high60 - low60)) * 100
        
        # 4. KD 指標
        rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean()
        d = k.ewm(com=2).mean()
        
        # 5. MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26
        macd = dif.ewm(span=9).mean()
        osc = dif - macd
        
        # 6. 新增：5日與10日績效 (作為勝率參考)
        # 計算邏輯：(目前價格 - N天前價格) / N天前價格
        ret_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(df) >= 6 else 0
        ret_10d = (close.iloc[-1] - close.iloc[-11]) / close.iloc[-11] * 100 if len(df) >= 11 else 0

        # --- 狀態判定 ---
        curr_bias = bias.iloc[-1]
        curr_k = k.iloc[-1]
        
        if curr_bias > 10: bias_txt = "🔴 危險"
        elif curr_bias > 5: bias_txt = "🟠 略貴"
        elif curr_bias < -5: bias_txt = "🟢 安全"
        else: bias_txt = "⚪ 合理"
        
        if curr_k > 80: kd_txt = "⚠️ 過熱"
        elif curr_k < 20: kd_txt = "🧊 超賣"
        else: kd_txt = "⚪ 整理"
        
        curr_osc = osc.iloc[-1]
        if curr_osc > 0 and curr_osc > osc.iloc[-2]: macd_txt = "⛽ 滿油"
        elif curr_osc > 0: macd_txt = "🚗 加速"
        else: macd_txt = "🛑 減速"

        return {
            "代號": code,
            "收盤價": last_price,
            "5日漲幅%": ret_5d,  # 對應您的 5日勝率需求
            "10日漲幅%": ret_10d, # 對應您的 10日勝率需求
            "乖離": bias_txt,
            "KD": kd_txt,
            "MACD": macd_txt,
            "位階%": pos.iloc[-1],
            "連結": f"https://tw.stock.yahoo.com/quote/{code}"
        }
    except: return None

# ==========================================
# 3. 頁面功能模組
# ==========================================

def page_dashboard():
    """庫存戰術看板 (還原回卡片+建議模式)"""
    st.header("📊 庫存戰術看板")
    if st.button("🔄 刷新"): st.rerun()

    cols = st.columns(3)
    for i, stock in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            data = get_smart_stock_data(stock["code"])
            with st.container(border=True):
                if data:
                    # 計算損益
                    mkt_val = data["price"] * stock["shares"]
                    cost_val = stock["cost"] * stock["shares"]
                    profit = mkt_val - cost_val
                    prof_pct = (profit / cost_val) * 100 if cost_val != 0 else 0
                    
                    st.subheader(f"{stock['name']} ({stock['code']})")
                    st.metric(f"收盤 ({data['date']})", f"{data['price']:.2f}", f"{data['change']:.2f} ({data['pct_change']:.2f}%)")
                    
                    color = ":red" if profit > 0 else ":green"
                    st.markdown(f"**損益**： {color}[{int(profit):,} ({prof_pct:.1f}%)]")
                    st.divider()
                    
                    # 戰術建議
                    st.markdown(f"💡 {generate_strategy_advice(prof_pct)}")
                    st.divider()
                    
                    # 連結
                    yahoo = f"https://tw.stock.yahoo.com/quote/{stock['code']}"
                    google = f"https://www.google.com/search?q={stock['name']}+新聞&tbm=nws"
                    st.markdown(f"[Yahoo 個股]({yahoo}) | [Google 新聞]({google})")
                else:
                    st.error("讀取失敗")

def page_scanner():
    """狙擊選股掃描 (維持表格模式 + 新增5日/10日)"""
    st.header("🎯 狙擊選股掃描")
    
    default = "2330, 2317, 2454, 2337, 4916, 8021, 2603, 3231"
    codes = st.text_area("輸入代號 (逗號分隔)", value=default)
    
    if st.button("🚀 執行掃描"):
        s_list = [x.strip() for x in codes.split(",")]
        res = []
        bar = st.progress(0)
        
        for i, c in enumerate(s_list):
            bar.progress((i+1)/len(s_list))
            d = get_dashboard_data(c)
            if d: res.append(d)
        
        bar.empty()
        
        if res:
            df = pd.DataFrame(res)
            st.dataframe(
                df,
                column_config={
                    "收盤價": st.column_config.NumberColumn(format="$%.2f"),
                    "5日漲幅%": st.column_config.NumberColumn(format="%.1f%%", help="近5日漲跌幅 (短期勝率參考)"),
                    "10日漲幅%": st.column_config.NumberColumn(format="%.1f%%", help="近10日漲跌幅 (波段勝率參考)"),
                    "位階%": st.column_config.ProgressColumn("位階%", format="%.0f%%", min_value=0, max_value=100),
                    "連結": st.column_config.LinkColumn("情報", display_text="分析")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("無資料")

def page_management():
    """庫存管理"""
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

# ==========================================
# 4. 主程式
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室")
    page = st.sidebar.radio("導航", ["📊 庫存戰術看板", "🎯 狙擊選股掃描", "➕ 庫存管理"])
    
    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "🎯 狙擊選股掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__":
    main()
