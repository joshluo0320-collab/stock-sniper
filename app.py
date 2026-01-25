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
# 2. 核心運算引擎 (KD, MACD, 乖離率)
# ==========================================
def calculate_indicators(df):
    # 1. 乖離率 (Bias20)
    ma20 = df['Close'].rolling(window=20).mean()
    bias = ((df['Close'] - ma20) / ma20) * 100
    
    # 2. 位階 (Position %) - 近60日高低點位置
    high60 = df['High'].rolling(window=60).max()
    low60 = df['Low'].rolling(window=60).min()
    position = ((df['Close'] - low60) / (high60 - low60)) * 100
    
    # 3. KD 指標 (9,3,3)
    rsv = (df['Close'] - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    
    # 4. MACD (12, 26, 9)
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    macd = dif.ewm(span=9, adjust=False).mean()
    osc = dif - macd
    
    return bias, k, d, osc, position

def get_dashboard_data(ticker_code):
    code = str(ticker_code)
    full_ticker = f"{code}.TW" if not code.endswith(('.TW', '.TWO')) else code
    
    try:
        # 抓取足夠資料以計算指標 (至少100天)
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="6mo") 
        
        if df.empty or len(df) < 60: return None
        
        # 計算所有指標
        bias, k, d, osc, pos = calculate_indicators(df)
        
        # 取得最後一筆數據
        last = df.iloc[-1]
        curr_bias = bias.iloc[-1]
        curr_k = k.iloc[-1]
        curr_d = d.iloc[-1]
        curr_osc = osc.iloc[-1]
        curr_pos = pos.iloc[-1]
        
        # --- 狀態判斷邏輯 (依照圖2風格) ---
        
        # 乖離狀況
        if curr_bias > 10: bias_status = f"🔴 危險 ({curr_bias:.1f}%)"
        elif curr_bias > 5: bias_status = f"🟠 略貴 ({curr_bias:.1f}%)"
        elif curr_bias < -5: bias_status = f"🟢 安全 ({curr_bias:.1f}%)"
        else: bias_status = f"⚪ 合理 ({curr_bias:.1f}%)"
        
        # KD狀態
        if curr_k > 80: kd_status = "⚠️ 過熱"
        elif curr_k > curr_d and curr_k < 80: kd_status = "🔥 續攻" # 黃金交叉向上
        elif curr_k < 20: kd_status = "🧊 超賣"
        else: kd_status = "⚪ 整理"
        
        # MACD動能
        if curr_osc > 0 and curr_osc > osc.iloc[-2]: macd_status = "⛽ 滿油" # 紅柱變長
        elif curr_osc > 0: macd_status = "🚗 加速" # 紅柱
        elif curr_osc < 0: macd_status = "🛑 減速" # 綠柱
        else: macd_status = "⚪ 平盤"

        # 停損/停利 (模擬計算：停損設MA20, 停利設前高)
        stop_loss = df['Close'].rolling(20).mean().iloc[-1] * 0.98 # MA20下方一點點
        take_profit = df['High'].rolling(60).max().iloc[-1]
        
        return {
            "代號": code,
            "收盤價": last['Close'],
            "乖離狀況": bias_status,
            "KD狀態": kd_status,
            "MACD動能": macd_status,
            "位階%": f"{curr_pos:.1f}",
            "停損": f"{stop_loss:.2f}",
            "停利": f"{take_profit:.2f}",
            "連結": f"https://tw.stock.yahoo.com/quote/{code}" # 簡易連結
        }
    except:
        return None

# ==========================================
# 3. 介面功能
# ==========================================

def page_dashboard():
    st.header("📊 庫存戰術看板")
    if st.button("🔄 刷新最新報價"): st.rerun()

    cols = st.columns(3)
    for i, stock in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            # 這裡簡化庫存顯示，重點放在下面的掃描表
            # 若要看庫存詳細數據，建議直接用掃描表看比較清楚
            pass 
            
    # 直接顯示庫存的「戰情儀表板」表格
    st.subheader("📋 庫存總體檢 (儀表板模式)")
    
    stock_data = []
    # 掃描庫存中的每一檔
    for stock in st.session_state.portfolio:
        data = get_dashboard_data(stock["code"])
        if data:
            # 補上名稱
            data["名稱"] = stock["name"]
            # 調整欄位順序
            ordered_data = {
                "代號": data["代號"],
                "名稱": data["名稱"],
                "收盤價": data["收盤價"],
                "乖離狀況": data["乖離狀況"],
                "KD狀態": data["KD狀態"],
                "MACD動能": data["MACD動能"],
                "位階%": data["位階%"],
                "停損": data["停損"],
                "停利": data["停利"],
                "連結": data["連結"]
            }
            stock_data.append(ordered_data)
            
    if stock_data:
        df = pd.DataFrame(stock_data)
        
        # 設定 DataFrame 顯示格式 (模仿圖2)
        st.dataframe(
            df,
            column_config={
                "收盤價": st.column_config.NumberColumn(format="$%.2f"),
                "位階%": st.column_config.ProgressColumn(
                    "位階%", 
                    help="股價在近60日高低點的位置", 
                    min_value=0, 
                    max_value=100,
                    format="%f%%"
                ),
                "連結": st.column_config.LinkColumn("查看情報", display_text="查看")
            },
            hide_index=True,
            use_container_width=True
        )

def page_scanner():
    st.header("🎯 狙擊選股掃描 (儀表板模式)")
    
    # 預設清單
    default_list = "2330, 2317, 2454, 2337, 4916, 8021, 2603, 3231, 3037"
    target_codes = st.text_area("輸入掃描代號 (逗號分隔)", value=default_list)
    
    if st.button("🚀 啟動戰情掃描"):
        stock_list = [x.strip() for x in target_codes.split(",")]
        results = []
        progress_bar = st.progress(0)
        
        for i, code in enumerate(stock_list):
            progress_bar.progress((i + 1) / len(stock_list))
            data = get_dashboard_data(code)
            
            if data:
                # 這裡不再過濾「不符合」的，而是顯示所有股票的「狀態」
                # 讓您自己決定哪一個燈號漂亮
                results.append(data)
                
        progress_bar.empty()
        
        if results:
            df = pd.DataFrame(results)
            
            # 使用 st.dataframe 的進階配置來達成圖2的效果
            st.dataframe(
                df,
                column_config={
                    "收盤價": st.column_config.NumberColumn(format="$%.2f"),
                    "位階%": st.column_config.ProgressColumn(
                        "位階%", 
                        min_value=0, 
                        max_value=100,
                        format="%.1f%%",
                    ),
                    "連結": st.column_config.LinkColumn("查看情報", display_text="分析")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("查無資料")

def page_management():
    st.header("➕ 庫存管理")
    with st.form("add_stock"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("股票代號")
        name = c2.text_input("股票名稱")
        shares = c3.number_input("持有股數", value=1000)
        cost = st.number_input("平均成本", value=100.0)
        if st.form_submit_button("新增"):
            st.session_state.portfolio.append({"code": code, "name": name, "cost": cost, "shares": shares})
            st.success(f"已新增 {name}")
            
    if st.session_state.portfolio:
        st.dataframe(pd.DataFrame(st.session_state.portfolio))
        idx = st.number_input("刪除索引", min_value=0, max_value=len(st.session_state.portfolio)-1, step=1)
        if st.button("🗑️ 刪除"):
            st.session_state.portfolio.pop(idx)
            st.rerun()

# ==========================================
# 4. 主程式入口
# ==========================================
def main():
    st.sidebar.title("🦅 戰情室導航")
    page = st.sidebar.radio("功能選單", ["🎯 狙擊選股掃描", "📊 庫存戰術看板", "➕ 庫存管理"]) # 把選股放第一個
    st.sidebar.markdown("---")
    st.sidebar.caption("v4.0 儀表板復刻版")

    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "🎯 狙擊選股掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__":
    main()
