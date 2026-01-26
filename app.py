import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import requests
from io import StringIO

# ==========================================
# 0. 系統基礎設定 (SSL & 連線)
# ==========================================
ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# ==========================================
# 1. 記憶與數據初始化
# ==========================================
st.set_page_config(page_title="鷹眼股市戰情室", page_icon="🦅", layout="wide")

# 初始化庫存 (若無則建立預設)
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {"code": "2337", "name": "旺宏", "cost": 32.35, "shares": 1000},
        {"code": "4916", "name": "事欣科", "cost": 64.0, "shares": 2000}
    ]

# 核心記憶：保留掃描結果，切換頁面不消失
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 2. 核心運算函數
# ==========================================

@st.cache_data(ttl=3600*24)
def get_all_tw_stocks_map():
    stock_map = {}
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        response = requests.get(url, headers=HEADERS, verify=False)
        response.encoding = 'big5'
        df = pd.read_html(StringIO(response.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df = df[df['CFICode'] == 'ESVUFR']
        for item in df['有價證券代號及名稱']:
            parts = item.split('\u3000')
            if len(parts) >= 2:
                code, name = parts[0].strip(), parts[1].strip()
                if len(code) == 4: stock_map[code] = name
    except:
        return {"2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2337": "旺宏", "4916": "事欣科"}
    return stock_map

def calculate_win_rate(df, days, target_pct):
    if len(df) < days + 1: return 0
    future_close = df['Close'].shift(-days) 
    returns = (future_close - df['Close']) / df['Close'] * 100
    wins = (returns >= target_pct).sum()
    total = returns.count()
    return (wins / total) * 100 if total > 0 else 0

def get_dashboard_data(ticker_code, min_vol, target_rise, min_win_rate_10d, forced_name=None):
    code = str(ticker_code)
    full_ticker = f"{code}.TW" if not code.endswith(('.TW', '.TWO')) else code
    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="1y") 
        if df.empty or len(df) < 60: return None
        if df['Volume'].iloc[-1] < min_vol * 1000: return None

        close = df['Close']
        last_price = close.iloc[-1]
        ma20 = close.rolling(20).mean()
        stop_loss = ma20.iloc[-1]
        
        # 鐵血濾網：強制股價 > MA20
        if last_price < stop_loss: return None

        win10 = calculate_win_rate(df, 10, target_rise)
        if win10 < min_win_rate_10d: return None
        
        win5 = calculate_win_rate(df, 5, target_rise)
        bias = ((last_price - stop_loss) / stop_loss) * 100
        
        return {
            "選取": True, "代號": code, "名稱": forced_name if forced_name else code,
            "收盤價": last_price, "停損價": stop_loss, "5日勝率%": win5, "10日勝率%": win10,
            "乖離": "🔴 危險" if bias > 10 else "🟠 略貴" if bias > 5 else "🟢 安全" if bias < -5 else "⚪ 合理",
            "連結": f"https://tw.stock.yahoo.com/quote/{code}"
        }
    except: return None

# ==========================================
# 3. 頁面模組
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板 (已自動更新報價)")
    
    cols = st.columns(3)
    for i, stock in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            try:
                t = yf.Ticker(f"{stock['code']}.TW")
                h = t.history(period="5d")
                if not h.empty:
                    last_p = h.iloc[-1]['Close']
                    prev_p = h.iloc[-2]['Close']
                    chg = last_p - prev_p
                    pct = (chg / prev_p) * 100
                    profit = (last_p - stock['cost']) * stock['shares']
                    prof_pct = (profit / (stock['cost'] * stock['shares'])) * 100
                    
                    # 顏色邏輯修正：漲紅跌綠
                    price_color = "red" if chg >= 0 else "green"
                    profit_color = "red" if profit >= 0 else "green"
                    
                    with st.container(border=True):
                        st.subheader(f"{stock['name']} ({stock['code']})")
                        st.markdown(f"現價：<span style='color:{price_color}; font-size:24px; font-weight:bold;'>{last_p:.2f}</span> ({chg:+.2f} / {pct:+.2f}%)", unsafe_allow_html=True)
                        st.markdown(f"損益：<span style='color:{profit_color}; font-weight:bold;'>{int(profit):+,} ({prof_pct:.2f}%)</span>", unsafe_allow_html=True)
                        st.divider()
                        
                        # 建議文字
                        advice = "🚀 獲利拉開，移動停利！" if prof_pct >= 10 else "📈 穩健獲利，續抱。" if prof_pct > 0 else "🛡️ 成本保衛。" if prof_pct > -5 else "🛑 嚴守停損！"
                        st.info(f"💡 {advice}")
            except: st.error(f"{stock['code']} 更新失敗")

def page_scanner():
    st.header("🎯 全市場自動掃描")
    stock_map = get_all_tw_stocks_map()
    all_codes = list(stock_map.keys())
    
    with st.sidebar:
        st.header("⚙️ 戰術控制台")
        min_vol = st.number_input("🌊 最低成交量 (張)", value=1000, step=100)
        target_rise = st.slider("🎯 目標漲幅 (%)", 1, 20, 10)
        min_win_rate = st.slider("🔥 最低10日勝率 (%)", 0, 100, 40)
        st.success("✅ 已強制開啟：股價 > 月線 (MA20)")

    if st.button("🚀 啟動全市場掃描", type="primary"):
        st.warning("🛑 掃描中... 如需停止請按右上角 Stop。")
        current_res = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, c in enumerate(all_codes):
            status.text(f"分析中：{c} {stock_map.get(c,'')}...")
            bar.progress((i+1)/len(all_codes))
            d = get_dashboard_data(c, min_vol, target_rise, min_win_rate, forced_name=stock_map.get(c))
            if d: 
                current_res.append(d)
                # 即時記憶，防止中斷消失
                st.session_state.scan_results = pd.DataFrame(current_res)

    # 顯示保留的搜尋結果
    if st.session_state.scan_results is not None:
        st.subheader("📋 掃描戰果 (已保留)")
        st.data_editor(
            st.session_state.scan_results,
            column_config={
                "收盤價": st.column_config.NumberColumn(format="%.2f"),
                "5日勝率%": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                "10日勝率%": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                "連結": st.column_config.LinkColumn(display_text="分析")
            },
            hide_index=True, use_container_width=True
        )

# ==========================================
# 4. 主程式
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室")
    page = st.sidebar.radio("導航", ["📊 庫存戰術看板", "🎯 全市場掃描", "➕ 庫存管理"])
    
    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "🎯 全市場掃描": page_scanner()
    elif page == "➕ 庫存管理":
        st.header("➕ 庫存管理")
        # (此處保留原有的增刪邏輯即可)
        st.write("請在此管理您的持股...")

if __name__ == "__main__":
    main()
