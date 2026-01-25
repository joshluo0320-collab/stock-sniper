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

# 狀態變數：用來暫存掃描結果，以免重新整理後消失
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

# ==========================================
# 2. 核心運算引擎
# ==========================================
def generate_strategy_advice(profit_pct):
    """庫存建議文字"""
    if profit_pct >= 10: return "🚀 **大獲全勝**：獲利拉開，移動停利設好，讓獲利奔跑！"
    elif 5 <= profit_pct < 10: return "📈 **穩健獲利**：表現不錯，續抱觀察。"
    elif 0 <= profit_pct < 5: return "🛡️ **成本保衛**：密切觀察，跌破成本需警戒。"
    elif -5 < profit_pct < 0: return "⚠️ **警戒狀態**：小幅虧損，檢查支撐。"
    else: return "🛑 **停損評估**：虧損擴大，嚴禁凹單！"

def get_stock_name(ticker, info):
    """嘗試取得中文名稱，若無則回傳代號"""
    try:
        # 優先抓取長名稱或短名稱
        name = info.get('longName') or info.get('shortName')
        if name:
            # 簡單處理：有時候 yf 回傳的是英文拼音 (如 TSMC)，這裡不做繁體轉換，直接顯示
            return name
    except:
        pass
    return ticker

def calculate_sniper_score(data_dict):
    """
    🎯 狙擊手評分機制 (0~100分)
    根據各項指標給予權重，計算「戰術勝率」
    """
    score = 60 # 基礎分
    
    # 1. 乖離率評分 (權重 20%)
    bias_str = data_dict['乖離']
    if "🟢 安全" in bias_str: score += 10
    elif "⚪ 合理" in bias_str: score += 5
    elif "🟠 略貴" in bias_str: score -= 5
    elif "🔴 危險" in bias_str: score -= 15
    
    # 2. KD指標評分 (權重 20%)
    kd_str = data_dict['KD']
    if "🔥 續攻" in kd_str: score += 10
    elif "⚪ 整理" in kd_str: score += 0
    elif "🧊 超賣" in kd_str: score += 5 (反彈機會)
    elif "⚠️ 過熱" in kd_str: score -= 5
    
    # 3. MACD動能評分 (權重 20%)
    macd_str = data_dict['MACD']
    if "⛽ 滿油" in macd_str: score += 15
    elif "🚗 加速" in macd_str: score += 10
    elif "🛑 減速" in macd_str: score -= 10
    
    # 4. 趨勢與近期績效 (權重 40%)
    # 簡單用 5日漲幅判斷強弱
    ret_5d = data_dict['raw_ret_5d']
    if ret_5d > 5: score += 10 # 強勢股
    elif ret_5d > 0: score += 5
    elif ret_5d < -5: score -= 10 # 弱勢股
    
    # 限制分數範圍 0-100
    score = max(0, min(100, score))
    return score

def get_dashboard_data(ticker_code):
    """掃描運算核心 (含名稱與直觀燈號)"""
    code = str(ticker_code)
    full_ticker = f"{code}.TW" if not code.endswith(('.TW', '.TWO')) else code
    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period="6mo")
        if df.empty or len(df) < 20: return None
        
        # 嘗試取得名稱 (這步驟會稍微拖慢速度，但為了顯示名稱是必須的)
        # 為了效能，若已經在庫存清單中有名字，可以直接用，這裡先全抓
        stock_name = get_stock_name(code, stock.info)
        
        # 1. 基礎數據
        close = df['Close']
        last_price = close.iloc[-1]
        
        # 2. 乖離率 (Bias20)
        ma20 = close.rolling(20).mean()
        bias = ((close - ma20) / ma20) * 100
        curr_bias = bias.iloc[-1]
        
        if curr_bias > 10: bias_txt = "🔴 危險"
        elif curr_bias > 5: bias_txt = "🟠 略貴"
        elif curr_bias < -5: bias_txt = "🟢 安全"
        else: bias_txt = "⚪ 合理"
        
        # 3. 位階
        high60 = df['High'].rolling(60).max()
        low60 = df['Low'].rolling(60).min()
        pos = ((close - low60) / (high60 - low60)) * 100
        
        # 4. KD 指標
        rsv = (close - df['Low'].rolling(9).min()) / (df['High'].rolling(9).max() - df['Low'].rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean()
        d = k.ewm(com=2).mean()
        curr_k = k.iloc[-1]
        
        if curr_k > 80: kd_txt = "⚠️ 過熱"
        elif curr_k > d.iloc[-1]: kd_txt = "🔥 續攻" # 黃金交叉或多頭排列
        elif curr_k < 20: kd_txt = "🧊 超賣"
        else: kd_txt = "⚪ 整理"
        
        # 5. MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26
        macd = dif.ewm(span=9).mean()
        osc = dif - macd
        curr_osc = osc.iloc[-1]
        
        if curr_osc > 0 and curr_osc > osc.iloc[-2]: macd_txt = "⛽ 滿油"
        elif curr_osc > 0: macd_txt = "🚗 加速"
        elif curr_osc < 0 and curr_osc > osc.iloc[-2]: macd_txt = "🔧 收腳" # 綠柱縮短
        else: macd_txt = "🛑 減速" # 綠柱變長

        # 6. 績效 (勝率參考)
        ret_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(df) >= 6 else 0
        ret_10d = (close.iloc[-1] - close.iloc[-11]) / close.iloc[-11] * 100 if len(df) >= 11 else 0

        return {
            "選取": True, # 預設打勾
            "代號": code,
            "名稱": stock_name,
            "收盤價": last_price,
            "乖離": bias_txt,
            "KD": kd_txt,
            "MACD": macd_txt,
            "位階%": pos.iloc[-1],
            "5日漲幅%": ret_5d,
            "raw_ret_5d": ret_5d, # 計算分數用原始數據
            "10日漲幅%": ret_10d,
            "連結": f"https://tw.stock.yahoo.com/quote/{code}"
        }
    except: return None

# ==========================================
# 3. 頁面功能模組
# ==========================================

def page_dashboard():
    """庫存戰術看板"""
    st.header("📊 庫存戰術看板")
    if st.button("🔄 刷新"): st.rerun()

    cols = st.columns(3)
    for i, stock in enumerate(st.session_state.portfolio):
        with cols[i % 3]:
            # 為了簡單顯示，這裡只抓簡易報價，不跑複雜運算
            # 實際使用建議將 get_dashboard_data 用在這邊會更詳細
            # 這裡維持您喜歡的卡片模式
            try:
                t = yf.Ticker(f"{stock['code']}.TW")
                h = t.history(period="5d")
                if not h.empty:
                    last = h.iloc[-1]
                    prev = h.iloc[-2]['Close']
                    price = last['Close']
                    chg = price - prev
                    pct = chg/prev*100
                    
                    # 計算損益
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
    """狙擊選股掃描 (決策增強版)"""
    st.header("🎯 狙擊選股掃描")
    
    default = "2330, 2317, 2454, 2337, 4916, 8021, 2603, 3231"
    codes = st.text_area("1. 輸入代號 (逗號分隔)", value=default)
    
    # --- 階段一：掃描 ---
    if st.button("🚀 啟動戰情掃描"):
        s_list = [x.strip() for x in codes.split(",")]
        res = []
        bar = st.progress(0)
        
        for i, c in enumerate(s_list):
            bar.progress((i+1)/len(s_list))
            d = get_dashboard_data(c)
            if d: res.append(d)
        
        bar.empty()
        
        if res:
            st.session_state.scan_results = pd.DataFrame(res)
        else:
            st.warning("無有效資料")

    # --- 階段二：篩選與評測 ---
    if st.session_state.scan_results is not None:
        st.subheader("2. 戰隊篩選 (請勾選想保留的股票)")
        st.info("💡 提示：在此處取消勾選「買不起」或「暫不考慮」的股票。")
        
        # 使用 data_editor 讓使用者可以打勾/取消打勾
        edited_df = st.data_editor(
            st.session_state.scan_results,
            column_config={
                "選取": st.column_config.CheckboxColumn("加入戰隊?", help="勾選以進行最終評測", default=True),
                "收盤價": st.column_config.NumberColumn(format="$%.2f"),
                "位階%": st.column_config.ProgressColumn("位階%", format="%.0f%%", min_value=0, max_value=100),
                "連結": st.column_config.LinkColumn("情報"),
                "raw_ret_5d": None # 隱藏計算欄位
            },
            disabled=["代號", "名稱", "收盤價", "乖離", "KD", "MACD", "位階%", "5日漲幅%", "10日漲幅%"], # 禁止編輯數據，只準勾選
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        
        # --- 階段三：最終評測 ---
        if st.button("🏆 開始評測 (計算勝率)"):
            # 1. 篩選出有打勾的
            final_df = edited_df[edited_df["選取"] == True].copy()
            
            if not final_df.empty:
                # 2. 計算評分
                final_df["戰術評分"] = final_df.apply(lambda row: calculate_sniper_score(row), axis=1)
                
                # 3. 排序 (高分在前)
                final_df = final_df.sort_values(by="戰術評分", ascending=False)
                
                st.subheader("🏅 最終勝率評測報告")
                
                # 顯示最終表格
                st.dataframe(
                    final_df[["名稱", "代號", "收盤價", "戰術評分", "乖離", "KD", "MACD"]],
                    column_config={
                        "戰術評分": st.column_config.ProgressColumn(
                            "AI 綜合評分", 
                            help="滿分100，越高代表技術面勝率越高",
                            format="%d 分",
                            min_value=0, 
                            max_value=100,
                        ),
                        "收盤價": st.column_config.NumberColumn(format="$%.2f")
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                # 冠軍展示
                top_stock = final_df.iloc[0]
                st.success(f"🏆 本次評測冠軍：**{top_stock['名稱']} ({top_stock['代號']})**，評分：{top_stock['戰術評分']} 分")
                
            else:
                st.error("您沒有選取任何股票！")

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
    page = st.sidebar.radio("導航", ["🎯 狙擊選股掃描", "📊 庫存戰術看板", "➕ 庫存管理"])
    
    if page == "📊 庫存戰術看板": page_dashboard()
    elif page == "🎯 狙擊選股掃描": page_scanner()
    elif page == "➕ 庫存管理": page_management()

if __name__ == "__main__":
    main()
