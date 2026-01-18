import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import plotly.graph_objects as go
from datetime import datetime, timedelta
import urllib3

# 忽略 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. 頁面設定
# ==========================================
st.set_page_config(
    page_title="Josh 的狙擊手戰情室 (極速穩定版)",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎯 Josh 的股市狙擊手戰情室")
st.markdown("### 專屬策略：多頭排列 + 爆量 + **雙勝率回測**")

# ==========================================
# 2. 側邊欄：參數與戰術看板
# ==========================================
st.sidebar.header("⚙️ 策略參數設定")

min_volume = st.sidebar.number_input("最低成交量 (張)", value=800, step=100)
vol_ratio = st.sidebar.slider("爆量係數 (今日 > N倍均量)", 1.0, 3.0, 1.2, 0.1)
rsi_min = st.sidebar.slider("RSI 最低門檻", 30, 70, 55)
rsi_max = st.sidebar.slider("RSI 最高門檻 (避免過熱)", 70, 100, 85)
ma_short = st.sidebar.number_input("短期均線 (MA)", value=20)
ma_long = st.sidebar.number_input("長期均線 (MA)", value=60)

st.sidebar.markdown("---")

# 進出場戰術看板
with st.sidebar.expander("⚔️ 狙擊手進出場戰術 (SOP)", expanded=True):
    st.markdown("""
    #### ✅ 進場檢查表 (Entry)
    1. **趨勢**：股價 > 月線 > 季線。
    2. **動能**：RSI 在 55~85。
    3. **籌碼**：爆量 > 5日均量 1.2倍。
    4. **位階**：近季高點附近。
    
    #### 🛑 出場準則 (Exit)
    1. **停損 (防守)**：
       - **跌破 月線(20MA)** ➜ 離場
