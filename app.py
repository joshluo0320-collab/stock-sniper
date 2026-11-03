from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf

# 1. 頁面基本配置
st.set_page_config(
    page_title="週動能波段與短線狙擊雙模組戰情室",
    page_icon="🏹",
    layout="wide",
)

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================
# 2. 核心工具與防呆保底載入
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
      res = requests.get(url, verify=False, timeout=5)
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

  # 🛡️ 防呆保底：若雲端開機抓不到清單，自動帶入常用標的避免崩潰
  if not names_map:
    names_map = {
        "2337": "旺宏",
        "3008": "大立光",
        "2330": "台積電",
        "2317": "鴻海",
        "2454": "聯發科",
    }
    tickers = ["2337.TW", "3008.TW", "2330.TW", "2317.TW", "2454.TW"]

  return tickers, names_map


def get_realtime_price_direct(tid):
  for suffix in [".TW", ".TWO"]:
    try:
      t = yf.Ticker(f"{tid}{suffix}")
      df_h = t.history(period="3d")
      if not df_h.empty:
        if isinstance(df_h.columns, pd.MultiIndex):
          df_h.columns = df_h.columns.get_level_values(0)
        df_h = df_h.dropna(subset=["Close"])
        if not df_h.empty:
          p = float(df_h["Close"].iloc[-1])
          d_str = df_h.index[-1].strftime("%m/%d")
          return round(p, 2), f"{d_str} (收盤)"
    except Exception:
      continue
  return None, "未知"


@st.cache_data(ttl=3600)
def check_market_macro_filter():
  try:
    df_market = yf.download("^TWII", period="3mo", progress=False, timeout=5)
    if df_market.empty:
      return True, 0, 0, "⚠️ 無法取得大盤資料，暫以預設通過處理。"

    if isinstance(df_market.columns, pd.MultiIndex):
      df_market.columns = df_market.columns.get_level_values(0)

    df_market["MA20"] = df_market["Close"].rolling(window=20).mean()
    curr_idx = float(df_market["Close"].iloc[-1])
    ma20_idx = float(df_market["MA20"].iloc[-1])

    is_healthy = curr_idx >= ma20_idx
    if is_healthy:
      msg = f"🟢 大盤多頭環境 (加權指數 {curr_idx:.2f} >= 月線 {ma20_idx:.2f})：多方結構完整。"
    else:
      msg = f"🔴 大盤逆風環境 (加權指數 {curr_idx:.2f} < 月線 {ma20_idx:.2f})：處於月線之下，建議提高警覺！"

    return is_healthy, round(curr_idx, 2), round(ma20_idx, 2), msg
  except Exception as e:
    return True, 0, 0, f"⚠️ 大盤檢驗逾時或異常，預設放行: {str(e)}"


# ============================================
# 3A. 庫存評估模型 (波段)
# ============================================
def evaluate_inventory_holding(tid, df_daily, cost_val):
  if df_daily.empty or len(df_daily) < 60:
    return None

  if isinstance(df_daily.columns, pd.MultiIndex):
    df_daily.columns = df_daily.columns.get_level_values(0)
  df_daily = df_daily.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

  curr_p, latest_date_str = get_realtime_price_direct(tid)
  if curr_p is None:
    curr_p = round(float(df_daily["Close"].iloc[-1]), 2)
    latest_date_str = df_daily.index[-1].strftime("%m/%d")

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

  if len(df_weekly) < 12:
    return None

  curr_w = df_weekly.iloc[-1]
  w_open = float(curr_w["Open"])
  w_high = float(curr_w["High"])
  w_low = float(curr_w["Low"])
  w_close = float(curr_w["Close"])
  w_vol = float(curr_w["Volume"]) / 1000.0

  ma5_w = round(float(df_weekly["Close"].rolling(5).mean().iloc[-1]), 2)
  ma10_w = round(float(df_weekly["Close"].rolling(10).mean().iloc[-1]), 2)
  high_4w = float(df_weekly["High"].tail(4).max())

  avg_vol_4w = float(df_weekly["Volume"].iloc[-5:-1].mean()) / 1000.0
  vol_ratio = round(w_vol / avg_vol_4w, 2) if avg_vol_4w > 0 else 1.0

  raw_roi = ((curr_p / cost_val) - 1) * 100

  if raw_roi >= 15.0:
    dynamic_stop = round(max(high_4w * 0.93, ma5_w, cost_val * 1.05), 1)
    stage_label = "🦅 長波段鎖利"
  elif raw_roi >= 5.0:
    dynamic_stop = round(max(cost_val * 1.01, min(w_low, ma5_w)), 1)
    stage_label = "🛡️ 保本推進"
  else:
    dynamic_stop = round(max(cost_val * 0.955, w_low), 1)
    stage_label = "🌱 新倉觀察"

  health_score = 50
  if curr_p >= ma5_w:
    health_score += 25
  else:
    health_score -= 20
  if curr_p >= ma10_w:
    health_score += 15
  health_score = max(0, min(100, health_score))

  if curr_p <= dynamic_stop:
    color_tag = "🔴 觸線出場"
    model_advice = f"🚨 跌破動態防守線 ({dynamic_stop})，建議收網獲利！"
  elif curr_p < ma5_w:
    color_tag = "🟡 趨勢轉弱"
    model_advice = f"⚠️ 跌破週 5MA ({ma5_w})，建議減碼"
  elif health_score >= 75:
    color_tag = "🟢 強勢續抱"
    model_advice = f"✅ 穩守週 5MA ({ma5_w}) 之上，可安心續抱"
  else:
    color_tag = "⚪ 正常觀察"
    model_advice = f"📈 守住防守線 ({dynamic_stop})，依紀律續抱"

  return {
      "curr_p": curr_p,
      "price_date": latest_date_str,
      "ma5_w": ma5_w,
      "vol_ratio": f"{vol_ratio}x",
      "health_score": health_score,
      "stage_label": stage_label,
      "dynamic_stop": dynamic_stop,
      "color_tag": color_tag,
      "model_advice": model_advice,
  }


# ============================================
# 3B. 全市場週動能掃描器 (波段)
# ============================================
def execute_weekly_sniper(
    df_daily, tid, name, min_price=30.0, max_price=200.0, min_weekly_vol=3000
):
  try:
    if df_daily.empty or len(df_daily) < 60:
      return None
    if isinstance(df_daily.columns, pd.MultiIndex):
      df_daily.columns = df_daily.columns.get_level_values(0)
    df_daily = df_daily.dropna(
        subset=["Open", "High", "Low", "Close", "Volume"]
    )

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
    win_score = min(score, 100)

    return {
        "名稱": name,
        "代號": tid,
        "動能評分": win_score,
        "最新收盤": last_p,
        "週量比": f"{round(vol_ratio, 2)}x",
        "週成交量(張)": int(curr_vol),
        "5週乖離": f"{round(bias_5w, 1)}%",
        "初始防守停損": round(curr_low, 1),
    }
  except Exception:
    return None


# ============================================
# 3C. 次日短線狙擊與風控模組 (短線)
# ============================================
def evaluate_next_day_momentum(df_daily, tid, name):
  try:
    if df_daily.empty or len(df_daily) < 30:
      return None
    if isinstance(df_daily.columns, pd.MultiIndex):
      df_daily.columns = df_daily.columns.get_level_values(0)
    df_daily = df_daily.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    curr_row = df_daily.iloc[-1]
    prev_row = df_daily.iloc[-2]
    c_open = float(curr_row["Open"])
    c_high = float(curr_row["High"])
    c_low = float(curr_row["Low"])
    c_close = float(curr_row["Close"])
    c_vol = float(curr_row["Volume"]) / 1000.0

    prev_close = float(prev_row["Close"])
    day_return_pct = ((c_close / prev_close) - 1) * 100
    avg_vol_20 = float(df_daily["Volume"].tail(20).mean()) / 1000.0

    total_range = c_high - c_low
    upper_shadow = c_high - max(c_close, c_open)
    is_clean_close = (
        (upper_shadow / total_range < 0.35) if total_range > 0 else True
    )

    # 隔日短線強勢條件：漲幅 >= 3%，收紅，上影線短，量放大
    if not (
        day_return_pct >= 3.0
        and c_close > c_open
        and is_clean_close
        and c_vol >= 3000
        and c_vol >= avg_vol_20
    ):
      return None

    entry_price = c_close
    stop_loss_price = round(min(c_low, entry_price * 0.975), 1)
    target_profit_3pct = round(entry_price * 1.03, 1)
    target_profit_5pct = round(entry_price * 1.05, 1)

    score = 50
    score += 20 if day_return_pct >= 7.0 else 10
    score = min(score, 100)

    return {
        "代號": tid,
        "名稱": name,
        "動能評分": score,
        "今日收盤價": c_close,
        "今日漲幅": f"{round(day_return_pct, 2)}%",
        "成交量(張)": int(c_vol),
        "建議進場參考": f"{entry_price} (收盤/明平開)",
        "🔴 嚴格停損價": stop_loss_price,
        "🟢 目標停利 (+3%)": target_profit_3pct,
        "🟢 目標停利 (+5%)": target_profit_5pct,
        "執行紀律提示": "開盤 30 分鐘內未見買盤續強或跌破停損立即出場！",
    }
  except Exception:
    return None


# ============================================
# 4. 側邊欄控制台
# ============================================
st.sidebar.header("🕹️ 雙模組策略控制台")
target_win = st.sidebar.slider("🎯 波段動能評分門檻", 50, 95, 70, step=5)
min_weekly_vol_input = st.sidebar.slider("🌊 週成交量門檻 (張)", 1000, 10000, 3000, step=500)

st.sidebar.markdown("---")
st.sidebar.subheader("📋 個人專屬庫存 (自動同步)")
default_inv = (
    st.query_params["inv"]
    if "inv" in st.query_params
    else "2337, 70, 1000, 2026-10-19\n3008, 4332.5, 10, 2026-10-19"
)
inventory_input = st.sidebar.text_area(
    "編輯持倉（修改後點下方按鈕）", value=default_inv, height=120
)
if st.sidebar.button("💾 儲存並更新專屬庫存網址", type="primary"):
  st.query_params["inv"] = inventory_input
  st.sidebar.success("✅ 已更新！")

# ============================================
# 5. 主頁面：雙模組分頁架構 (Tabs)
# ============================================
st.title("🏹 智能動能戰情與風控系統 (雙模組整合版)")

# 載入市場代號
_, names_map = get_market_map()

# 建立分頁
tab_wave, tab_short = st.tabs(
    ["📊 長線波段戰情室 (Holding)", "⚡ 次日短線狙擊戰情室 (Day/Next-Day)"]
)

# --- 標籤一：長線波段戰情室 ---
with tab_wave:
  st.subheader("📊 庫存週線體質診斷與移動鎖利戰情室")
  inv_lines = [
      l.strip()
      for l in inventory_input.split("\n")
      if "," in l and l.strip() != ""
  ]

  if inv_lines:
    inv_data = []
    for line in inv_lines:
      parts = [p.strip() for p in line.split(",")]
      try:
        tid, cost_val = parts[0], float(parts[1])
        shares = int(float(parts[2])) if len(parts) >= 3 and not ("-" in parts[2] or "/" in parts[2]) else 1000
        
        df = yf.download(f"{tid}.TW", period="1y", progress=False)
        if df.empty:
          df = yf.download(f"{tid}.TWO", period="1y", progress=False)

        eval_res = evaluate_inventory_holding(tid, df, cost_val)
        if eval_res:
          curr_p = eval_res["curr_p"]
          stock_name = names_map.get(tid, tid)
          invested = int(cost_val * shares)
          market_val = int(curr_p * shares)
          profit = market_val - invested
          roi = round((profit / invested) * 100, 2) if invested > 0 else 0

          inv_data.append({
              "代號": tid,
              "名稱": stock_name,
              "持有股數": f"{shares:,}",
              "成本": cost_val,
              "現價": curr_p,
              "預估淨損益": f"{profit:+,} 元",
              "報酬率": f"{roi:+.2f}%",
              "階段": eval_res["stage_label"],
              "週5MA": eval_res["ma5_w"],
              "動態防守線": eval_res["dynamic_stop"],
              "燈號": eval_res["color_tag"],
              "診斷": eval_res["model_advice"],
          })
      except Exception:
        continue
    if inv_data:
      st.dataframe(pd.DataFrame(inv_data), use_container_width=True)

  st.markdown("---")
  st.subheader("🌐 大盤宏觀環境檢視與全市場週動能掃描")
  market_ok, m_idx, m_ma20, market_msg = check_market_macro_filter()
  if market_ok:
    st.success(market_msg)
  else:
    st.error(market_msg)

  if st.button("🔴 啟動全市場週動能波段掃描", type="primary"):
    effective_target_win = target_win if market_ok else min(target_win + 10, 95)
    final_results = []
    tickers, _ = get_market_map()
    with st.spinner("📡 正在掃描全台股週線動能..."):
      for i in range(0, len(tickers), 60):
        chunk = tickers[i : i + 60]
        try:
          data = yf.download(
              chunk, period="1y", group_by="ticker", progress=False
          )
          for t in chunk:
            tid = t.split(".")[0]
            df_stock = data[t] if len(chunk) > 1 else data
            res = execute_weekly_sniper(df_stock, tid, names_map.get(tid, tid))
            if res and res["動能評分"] >= effective_target_win:
              final_results.append(res)
        except Exception:
          continue
    if final_results:
      st.dataframe(
          pd.DataFrame(final_results).sort_values(
              by="動能評分", ascending=False
          ),
          use_container_width=True,
      )
    else:
      st.warning("⚠️ 目前無標的符合週線強勢突破條件，建議保持現金觀望。")

# --- 標籤二：次日短線狙擊戰情室 ---
with tab_short:
  st.subheader("⚡ 次日短線強勢狙擊與風控戰情室 (Next-Day Momentum)")
  st.caption(
      "💡 專為極短線設計：篩選強勢鎖碼、量能放大標的，提供明確進場、停損與 3%~5% 停利目標。"
  )

  col_f1, col_f2 = st.columns(2)
  with col_f1:
    total_capital = st.number_input(
        "可用短線資金總額 (NT$)", value=270000, step=10000
    )
  with col_f2:
    allocation_pct = st.slider("單筆短線試單佔總資金比例 (%)", 5, 30, 10, step=5)

  allocated_funds = int(total_capital * (allocation_pct / 100))
  st.info(
      f"💰 資金風控提示：單筆短線試單金額為 **NT$ {allocated_funds:,}"
      "**（嚴格控制極小部位，風險可控）。"
  )

  if st.button("🚀 執行次日短線標的掃描", type="primary"):
    short_results = []
    tickers, _ = get_market_map()
    with st.spinner("⚡ 正在過濾短線爆量強勢標的..."):
      for i in range(0, len(tickers), 60):
        chunk = tickers[i : i + 60]
        try:
          data = yf.download(
              chunk, period="60d", group_by="ticker", progress=False
          )
          for t in chunk:
            tid = t.split(".")[0]
            df_stock = data[t] if len(chunk) > 1 else data
            res = evaluate_next_day_momentum(
                df_stock, tid, names_map.get(tid, tid)
            )
            if res:
              short_results.append(res)
        except Exception:
          continue

    if short_results:
      st.success(f"🎯 成功篩選出 {len(short_results)} 檔次日短線強勢候選標的：")
      df_short = pd.DataFrame(short_results).sort_values(
          by="動能評分", ascending=False
      )
      df_short.index = range(1, len(df_short) + 1)
      st.dataframe(df_short, use_container_width=True)
    else:
      st.warning(
          "⚠️ 今日盤面無符合「爆量強勢收高」條件的短線標的。空手也是一種防守。"
      )
