import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 1. 核心邏輯：v23.2 數據格式化
# ============================================
def execute_sniper_v23(df, tid, name, vol_gate, trail_p, max_budget):
    if df.empty or len(df) < 40: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    last_p = round(float(df['Close'].iloc[-1]), 1)  # <--- 修正 2: 顯示至小數點第一位
    if last_p > max_budget: return None

    # ATR 波動率計算
    tr = pd.concat([
        df['High'] - df['Low'], 
        abs(df['High'] - df['Close'].shift(1)), 
        abs(df['Low'] - df['Close'].shift(1))
    ], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean().iloc[-1]
    volatility_ratio = (atr_14 / last_p) * 100
    
    # 邏輯計算
    ma5 = df['Close'].rolling(5).mean().iloc[-1]
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd_slope = (ema_12 - ema_26).diff().iloc[-1]
    is_break = last_p > df['High'].rolling(20).max().shift(1).iloc[-1]
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5 if avg_v_5 > 0 else 0

    # 勝率與動態撤退線
    total_score = int(( (50 if last_p > ma5 else 0) * 0.4) + ((50 if macd_slope > 0 else -20) * 0.6) + (10 if is_break else 0))
    dynamic_trail = min(max(trail_p, 3.5), 7.0) 
    # <--- 修正 2: 撤退線顯示至小數點第一位
    withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - dynamic_trail/100)), 1)

    return {
        "名稱": name, "代號": tid, "勝率": f"{total_score}%",
        "現價": last_p, "撤退線": withdrawal_line, 
        "波動力(ATR)": f"{round(volatility_ratio, 2)}%",
        "油門": "🏎️ 加速" if macd_slope > 0 else "🐢 減速",
        "能量": "⛽ 爆量" if v_ratio > 1.5 else "🚗 正常",
        "路況": "🛣️ 無壓" if is_break else "🚧 有牆",
        "建議進場區": f"{round(last_p * 0.98, 1)}~{round(last_p * 0.995, 1)}"
    }

# ============================================
# 2. UI 介面設定 (修正 1: 控制門檻單位)
# ============================================
st.set_page_config(page_title="獵殺系統 v23.2", layout="wide")
st.sidebar.header("🕹️ 獵殺控制台")

# 修正 1: 勝率門檻 (5%一單位), 均張 (500一單位), 止盈回落 (1%一單位)
target_win = st.sidebar.slider("🎯 勝率門檻 (%)", 10, 95, 60, step=5)
vol_limit = st.sidebar.slider("🌊 均張門檻", 0, 10000, 500, step=500)
trail_pct = st.sidebar.slider("🛡️ 止盈回落 (%)", 1.0, 15.0, 5.0, step=1.0)

max_budget = st.sidebar.number_input("💸 單張上限 (元)", value=250)
st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area("📋 庫存監控 (代號,成本)", value="2337,34")

st.title("🏹 2026 獵殺系統 v23.2")

# --- 庫存與全市場邏輯同前 (略) ---
