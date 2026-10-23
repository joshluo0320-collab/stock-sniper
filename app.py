import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf
from bs4 import BeautifulSoup

# 1. 頁面基本配置（必須是第一個執行的 Streamlit 語句）
st.set_page_config(page_title="週動能獵殺系統 v24.1", layout="wide")

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================
# 2. 週動能波段核心邏輯 (Weekly Momentum Swing)
# ============================================
def execute_weekly_sniper(
    df_daily, tid, name, min_price=30.0, max_price=200.0, min_weekly_vol=3000
):
  """平日/假日相容：週線級別動能突破與階梯式風控模型"""
  try:
    if df_daily.empty or len(df_daily) < 60:
      return None

    if isinstance(df_daily.columns, pd.MultiIndex):
      df_daily.columns = df_daily.columns.get_level_values(0)
    df_daily = df_daily.dropna(
        subset=["Open", "High", "Low", "Close", "Volume"]
    )

    if len(df_daily) < 60:
      return None

    latest_trade_date = df_daily.index[-1].strftime("%Y-%m-%d")
    last_p = round(float(df_daily["Close"].iloc[-1]), 1)

    if not (min_price <= last_p <= max_price):
      return None

    df_weekly = (
        df_daily.resample("W-FRI")
        .agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        })
        .dropna()
    )

    if len(df_weekly) < 15:
      return None

    curr_w = df_weekly.iloc[-1]
    curr_close = float(curr_w["Close"])
    curr_high = float(curr_w["High"])
    curr_low = float(curr_w["Low"])
    curr_open = float(curr_w["Open"])
    curr_vol = float(curr_w["Volume"]) / 1000.0

    if curr_vol < min_weekly_vol:
      return None

    ma5_w = df_weekly["Close"].rolling(5).mean().iloc[-1]
    ma10_w = df_weekly["Close"].rolling(10).mean().iloc[-1]

    bias_5w = ((curr_close / ma5_w) - 1) * 100
    if bias_5w > 12.0:
      return None

    prev_4w_high = df_weekly["High"].iloc[-5:-1].max()
    is_break_4w = curr_close > prev_4w_high

    avg_vol_4w = df_weekly["Volume"].iloc[-5:-1].mean() / 1000.0
    vol_ratio = curr_vol / avg_vol_4w if avg_vol_4w > 0 else 0

    total_range = curr_high - curr_low
    upper_shadow = curr_high - max(curr_close, curr_open)
    body = abs(curr_close - curr_open)

    is_bullish = curr_close >= curr_open
    is_clean_candle = (
        (upper_shadow / total_range < 0.35) if total_range > 0 else True
    )

    if not (
        curr_close > ma5_w
        and curr_close > ma10_w
        and is_break_4w
        and vol_ratio >= 1.3
        and is_bullish
        and is_clean_candle
    ):
      return None

    score = 50
    score += 20 if vol_ratio >= 1.8 else 10
    high_12w = df_weekly["High"].iloc[-13:-1].max()
    is_super_break = curr_close > high_12w
    score += 15 if is_super_break else 0
    score += (
        15 if (body / total_range >= 0.6 if total_range > 0 else False) else 5
    )
    win_score = min(score, 100)

    entry_ref = last_p
    risk_floor = max(curr_low, round(entry_ref * 0.955, 1))
    hard_stop_loss = round(risk_floor, 1)

    breakeven_trigger = round(entry_ref * 1.05, 1)
    target_lock_p = round(entry_ref * 1.08, 1)

    is_super_strong = is_super_break and (vol_ratio >= 1.8)
    weekly_stance = "🚀 強動能主升" if is_super_strong else "📈 標準突破"

    return {
        "名稱": name,
        "代號": tid,
        "動能評分": win_score,
        "最新收盤": last_p,
        "資料基準日": latest_trade_date,
        "週量比": f"{round(vol_ratio, 2)}x",
        "週成交量(張)": int(curr_vol),
        "形態": weekly_stance,
        "5週乖離": f"{round(bias_5w, 1)}%",
        "建議進場參考": f"{entry_ref} ~ {round(entry_ref * 1.01, 1)}",
        "初始防守停損": hard_stop_loss,
        "保本觸發線(+5%)": breakeven_trigger,
        "目標鎖利點(+8%)": target_lock_p,
        "週五操作策略": (
            "週五 13:00 全數了結"
            if not is_super_strong
            else "創季高可留半倉，其餘出場"
        ),
    }
  except Exception:
    return None


# ============================================
# 3. 名單抓取工具 (上市與上櫃股票代號)
# ============================================
@st.cache_data(ttl=86400)
def get_market_map():
  tickers, names_map = [], {}
  urls = [
      "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
      "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
  ]
  for url in urls:
    try:
      res = requests.get(url, verify=False, timeout=10)
      res.encoding = "big5"
      soup = BeautifulSoup(res.text, "lxml")
      for row in soup.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) > 0:
          raw = tds[0].text.strip().split()
          if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
            suffix = ".TW" if "strMode=2" in url else ".TWO"
            tickers.append(f"{raw[0]}{suffix}")
            names_map[raw[0]] = raw[1]
    except Exception:
      continue
  return tickers, names_map


# ============================================
# 4. 側邊欄控制項
# ============================================
st.sidebar.header("🕹️ 週輪動控制台 v24.1")
target_win = st.sidebar.slider("🎯 動能評分門檻", 50, 95, 70, step=5)
min_weekly_vol_input = st.sidebar.slider(
    "🌊 週成交量門檻 (張)", 1000, 10000, 3000, step=500
)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 股價自選區間")
min_price_input = st.sidebar.number_input("最低股價 (元)", value=30.0, step=5.0)
max_price_input = st.sidebar.number_input(
    "最高股價 (元)", value=180.0, step=10.0
)

st.sidebar.markdown("---")
inventory_input = st.sidebar.text_area(
    "📋 庫存監控 (代號,成本,買進日[可選])", value="2337,70,2026-10-19"
)

# ============================================
# 5. 主頁面內容
# ============================================
st.title("🏹 2026 週級別動能輪動系統 (平日/週末全相容版)")
st.caption(
    "💡 核心紀律：週末選股 ➔ 週一開盤進場 ➔ 週間智慧停損/保本 ➔ 週五 13:00"
    " 無條件清倉變現（免受週末利空影響）"
)

# --- A. 庫存檢視模組 (戰情室升級版) ---
st.subheader("📊 庫存動態與週結算戰情室")

inv_lines = [
    l.strip()
    for l in inventory_input.split("\n")
    if "," in l and l.strip() != ""
]

if inv_lines:
  inv_data = []
  today_date = pd.Timestamp.now()
  is_friday = today_date.weekday() == 4

  for line in inv_lines:
    parts = [p.strip() for p in line.split(",")]
    tid = parts[0]
    cost_val = float(parts[1])
    buy_date = parts[2] if len(parts) >= 3 else "未指定"

    df = yf.download(f"{tid}.TW", period="6mo", progress=False)
    if df.empty:
      df = yf.download(f"{tid}.TWO", period="6mo", progress=False)

    if not df.empty:
      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      curr_p = round(float(df["Close"].iloc[-1]), 1)
      p_l = round((curr_p / cost_val - 1) * 100, 2)

      hard_stop = round(cost_val * 0.955, 1)
      be_trigger = round(cost_val * 1.05, 1)
      target_p = round(cost_val * 1.08, 1)

      if curr_p <= hard_stop:
        action = "🚨 觸及停損 (立即出場)"
        color_tag = "🔴 停損"
      elif is_friday:
        action = (
            "⏳ 週五結算日 (13:00 清倉變現)"
            if curr_p < target_p
            else "🚀 達標！收網獲利"
        )
        color_tag = "🟡 結算"
      elif curr_p >= be_trigger:
        action = "🛡️ 已達 +5%，券商掛成本價保本"
        color_tag = "🟢 保本"
      else:
        action = "📈 正常抱牢中"
        color_tag = "⚪ 持續"

      inv_data.append({
          "代號": tid,
          "買進日": buy_date,
          "成本價": cost_val,
          "當前現價": curr_p,
          "盈虧幅度": f"{p_l}%",
          "初始停損(-4.5%)": hard_stop,
          "保本線(+5%)": be_trigger,
          "目標線(+8%)": target_p,
          "戰術燈號": color_tag,
          "當前執行指引": action,
          "raw_p_l": p_l,
      })

  if inv_data:
    df_inv = pd.DataFrame(inv_data)

    col1, col2, col3, col4 = st.columns(4)
    avg_return = df_inv["raw_p_l"].mean()
    col1.metric("總持倉檔數", f"{len(df_inv)} 檔")
    col2.metric("整體平均盈虧", f"{round(avg_return, 2)}%")
    col3.metric("最高獲利標的", f"{df_inv['raw_p_l'].max()}%")
    alert_count = len(
        df_inv[df_inv["戰術燈號"].isin(["🔴 停損", "🟡 結算"])]
    )
    col4.metric("需即時處理", f"{alert_count} 檔")

    display_df = df_inv.drop(columns=["raw_p_l"])
    display_df.index = range(1, len(display_df) + 1)
    st.dataframe(display_df, use_container_width=True)
else:
  st.info("💡 請在側邊欄庫存監控輸入持倉，格式範例：`2337, 70, 2026-10-19`")

st.markdown("---")

# --- B. 全市場週動能掃描模組 ---
if st.button("🔴 啟動全市場週動能掃描 (全台股)", type="primary"):
  final_results = []
  tickers, names_map = get_market_map()

  with st.status(
      f"📡 正在掃描台股全標的週線動能... 總計檔數：{len(tickers)} 檔",
      expanded=True,
  ) as status:
    pb = st.progress(0)
    chunk_size = 60

    for i in range(0, len(tickers), chunk_size):
      chunk = tickers[i : i + chunk_size]
      pb.progress(min((i + chunk_size) / len(tickers), 1.0))
      try:
        data = yf.download(
            chunk, period="1y", group_by="ticker", progress=False
        )
        for t in chunk:
          tid = t.split(".")[0]
          df_stock = data[t] if len(chunk) > 1 else data

          res = execute_weekly_sniper(
              df_stock,
              tid,
              names_map.get(tid, tid),
              min_price=min_price_input,
              max_price=max_price_input,
              min_weekly_vol=min_weekly_vol_input,
          )

          if res and res["動能評分"] >= target_win:
            final_results.append(res)
      except Exception:
        continue

    status.update(label="🎯 全市場週動能掃描完成！", state="complete")

  if final_results:
    st.subheader(
        f"🏆 次週優先佈局名單 (股價: {int(min_price_input)}~{int(max_price_input)}"
        f" 元，評分門檻: {target_win} 分)"
    )
    df_res = pd.DataFrame(final_results).sort_values(
        by="動能評分", ascending=False
    )
    df_res.index = range(1, len(df_res) + 1)
    st.dataframe(df_res, use_container_width=True)
  else:
    st.warning(
        "⚠️ 目前無標的符合週線強勢突破條件。在多頭力道不足時，建議保留現金觀望。"
    )
