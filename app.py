from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf

# 1. 頁面基本配置
st.set_page_config(
    page_title="週動能獵殺與持倉巡航系統 v25.0 (大盤濾網版)",
    page_icon="🏹",
    layout="wide",
)

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================
# 2. 名單抓取與大盤總開關工具
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


def check_market_macro_filter():
  """下載台股加權指數 (^TWII)，檢驗是否站上 20MA (月線)"""
  try:
    df_market = yf.download("^TWII", period="3mo", progress=False)
    if df_market.empty:
      return True, 0, 0, "⚠️ 無法取得大盤資料，暫以預設通過處理。"

    if isinstance(df_market.columns, pd.MultiIndex):
      df_market.columns = df_market.columns.get_level_values(0)

    df_market["MA20"] = df_market["Close"].rolling(window=20).mean()
    curr_idx = float(df_market["Close"].iloc[-1])
    ma20_idx = float(df_market["MA20"].iloc[-1])

    is_healthy = curr_idx >= ma20_idx

    if is_healthy:
      msg = f"🟢 大盤多頭環境 (加權指數 {curr_idx:.2f} >= 月線 {ma20_idx:.2f})：多方結構完整，正常執行掃描。"
    else:
      msg = f"🔴 大盤逆風環境 (加權指數 {curr_idx:.2f} < 月線 {ma20_idx:.2f})：處於月線之下，建議提高警覺或空倉觀望！"

    return is_healthy, round(curr_idx, 2), round(ma20_idx, 2), msg
  except Exception as e:
    return True, 0, 0, f"⚠️ 大盤檢驗異常: {str(e)}"


# ============================================
# 3A. 庫存股專用：週線體質與續抱評估模型
# ============================================
def evaluate_inventory_holding(df_daily, cost_val):
  if df_daily.empty or len(df_daily) < 60:
    return None

  if isinstance(df_daily.columns, pd.MultiIndex):
    df_daily.columns = df_daily.columns.get_level_values(0)
  df_daily = df_daily.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

  curr_p = round(float(df_daily["Close"].iloc[-1]), 2)

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

  w_range = w_high - w_low
  upper_shadow = w_high - max(w_close, w_open)
  is_shooting_star = (
      ((upper_shadow / w_range) > 0.45 and vol_ratio > 1.6)
      if w_range > 0
      else False
  )

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

  if w_close >= w_open and not is_shooting_star:
    health_score += 10
  elif is_shooting_star:
    health_score -= 15

  health_score = max(0, min(100, health_score))

  if curr_p <= dynamic_stop:
    color_tag = "🔴 觸線出場"
    model_advice = (
        f"🚨 跌破動態防守線 ({dynamic_stop})，建議收網獲利/停損落袋！"
    )
  elif curr_p < ma5_w:
    color_tag = "🟡 趨勢轉弱"
    model_advice = f"⚠️ 跌破週 5MA ({ma5_w})，動能衰退，建議週五減碼或了結"
  elif is_shooting_star:
    color_tag = "🟡 爆量上影"
    model_advice = "⚠️ 本週出現爆量長上影線，主力有調節跡象，建議先出一半鎖利"
  elif health_score >= 75:
    color_tag = "🟢 強勢續抱"
    model_advice = (
        f"✅ 穩守週 5MA ({ma5_w}) 之上，週線多頭完整，可安心續抱過週末"
    )
  else:
    color_tag = "⚪ 正常觀察"
    model_advice = f"📈 守住防守線 ({dynamic_stop})，依紀律續抱觀察"

  return {
      "curr_p": curr_p,
      "ma5_w": ma5_w,
      "vol_ratio": f"{vol_ratio}x",
      "health_score": health_score,
      "stage_label": stage_label,
      "dynamic_stop": dynamic_stop,
      "color_tag": color_tag,
      "model_advice": model_advice,
  }


# ============================================
# 3B. 全市場掃描專用：週動能突破篩選器
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
            else "創季高可留半倉，並移入庫存追蹤"
        ),
    }
  except Exception:
    return None


# ============================================
# 4. 側邊欄控制項與狀態初始化
# ============================================
st.sidebar.header("🕹️ 週輪動控制台 v25.0")
target_win = st.sidebar.slider("🎯 掃描動能評分門檻", 50, 95, 70, step=5)
min_weekly_vol_input = st.sidebar.slider(
    "🌊 週成交量門檻 (張)", 1000, 10000, 3000, step=500
)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 掃描股價區間")
min_price_input = st.sidebar.number_input("最低股價 (元)", value=30.0, step=5.0)
max_price_input = st.sidebar.number_input(
    "最高股價 (元)", value=180.0, step=10.0
)

if "inventory_text" not in st.session_state:
  st.session_state["inventory_text"] = "2337, 70, 1000, 2026-10-19"

# ============================================
# 5. 主頁面內容
# ============================================
st.title("🏹 2026 週級別動能輪動系統 (大盤月線濾網防護版)")
st.caption(
    "💡 核心機制：結合『大盤月線總開關』與『動態移動防守線』，在逆風環境自動提高篩選標準，過濾假突破雜訊。"
)

# 🔄 跨裝置設定碼同步面板
with st.expander(
    "🔄 【跨裝置同步】點此展開：匯出或匯入您的庫存設定碼", expanded=False
):
  col_ex, col_im = st.columns(2)
  with col_ex:
    st.markdown("**1️⃣ 從本機匯出設定碼**")
    st.code(st.session_state["inventory_text"], language="text")
  with col_im:
    st.markdown("**2️⃣ 在此貼上並載入設定碼**")
    imported_code = st.text_area(
        "貼上設定碼", value=st.session_state["inventory_text"], height=80
    )
    if st.button("📥 立即載入並套用設定碼", type="primary"):
      st.session_state["inventory_text"] = imported_code
      st.success("✅ 庫存已同步更新完成！")
      st.rerun()

inventory_input = st.session_state["inventory_text"]
_, names_map = get_market_map()

# --- A. 庫存檢視模組 ---
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
      tid = parts[0]
      cost_val = float(parts[1])
      shares = 1000
      buy_date = "未指定"

      if len(parts) == 3:
        if "-" in parts[2] or "/" in parts[2]:
          buy_date = parts[2]
        else:
          shares = int(float(parts[2]))
      elif len(parts) >= 4:
        shares = int(float(parts[2]))
        buy_date = parts[3]

      df = yf.download(f"{tid}.TW", period="1y", progress=False)
      if df.empty:
        df = yf.download(f"{tid}.TWO", period="1y", progress=False)

      eval_res = evaluate_inventory_holding(df, cost_val)
      if eval_res:
        curr_p = eval_res["curr_p"]
        stock_name = names_map.get(tid, tid)

        raw_cost_total = cost_val * shares
        buy_fee = max(1, int(raw_cost_total * 0.001425))
        total_invested = int(raw_cost_total + buy_fee)

        gross_market_val = curr_p * shares
        sell_fee_tax = max(1, int(gross_market_val * (0.001425 + 0.003)))
        net_market_val = int(gross_market_val - sell_fee_tax)

        net_profit_ntd = net_market_val - total_invested
        p_l_pct = round((net_profit_ntd / total_invested) * 100, 2)

        inv_data.append({
            "代號": tid,
            "名稱": stock_name,
            "持有股數": f"{shares:,} 股",
            "成本均價": cost_val,
            "當前現價": curr_p,
            "預估淨損益": f"{net_profit_ntd:+,} 元",
            "淨報酬率": f"{p_l_pct:+.2f}%",
            "持倉階段": eval_res["stage_label"],
            "週5MA生命線": eval_res["ma5_w"],
            "動態鎖利/防守線": eval_res["dynamic_stop"],
            "週體質分": f"{eval_res['health_score']} 分",
            "續抱燈號": eval_res["color_tag"],
            "模型續抱/出場診斷": eval_res["model_advice"],
            "raw_invested": total_invested,
            "raw_market_val": net_market_val,
            "raw_profit": net_profit_ntd,
        })
    except Exception:
      continue

  if inv_data:
    df_inv = pd.DataFrame(inv_data)
    sum_invested = df_inv["raw_invested"].sum()
    sum_market = df_inv["raw_market_val"].sum()
    sum_profit = df_inv["raw_profit"].sum()
    total_roi = (
        round((sum_profit / sum_invested) * 100, 2) if sum_invested > 0 else 0.0
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總投入成本 (含摩擦)", f"NT$ {sum_invested:,}")
    col2.metric("當前淨市值", f"NT$ {sum_market:,}")
    col3.metric(
        "帳面總淨損益",
        f"NT$ {sum_profit:+,}",
        delta=f"{total_roi:+.2f}%",
    )
    alert_count = len(
        df_inv[
            df_inv["續抱燈號"].isin([
                "🔴 觸線出場",
                "🟡 趨勢轉弱",
                "🟡 爆量上影",
            ])
        ]
    )
    col4.metric("需減碼/出場警示", f"{alert_count} / {len(df_inv)} 檔")

    display_df = df_inv.drop(
        columns=["raw_invested", "raw_market_val", "raw_profit"]
    )
    display_df.index = range(1, len(display_df) + 1)
    st.dataframe(display_df, use_container_width=True)
else:
  st.info("💡 請透過上方設定碼面板輸入您的持倉內容。")

st.markdown("---")

# --- B. 全市場週動能掃描模組 (已連動大盤月線濾網) ---
st.subheader("🌐 大盤宏觀環境檢視 (月線總開關)")
market_ok, m_idx, m_ma20, market_msg = check_market_macro_filter()

if market_ok:
  st.success(market_msg)
else:
  st.error(market_msg)

if st.button("🔴 啟動全市場週動能掃描 (尋找下週新獵物)", type="primary"):
  # 🛡️ 智慧動態門檻調整：若大盤逆風，自動將評分門檻拉高 10 分以策安全
  if not market_ok:
    effective_target_win = min(target_win + 10, 95)
    st.warning(
        f"⚠️ 偵測到大盤處於月線之下（逆風環境），系統已自動將動能評分門檻從"
        f" {target_win} 分提高至【 {effective_target_win} 分】進行嚴格過濾！"
    )
  else:
    effective_target_win = target_win
    st.info(f"🎯 本次掃描動能評分門檻：{effective_target_win} 分")

  final_results = []
  tickers, _ = get_market_map()

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

          # 採用動態調整後的門檻進行篩選
          if res and res["動能評分"] >= effective_target_win:
            final_results.append(res)
      except Exception:
        continue

    status.update(label="🎯 全市場週動能掃描完成！", state="complete")

  if final_results:
    st.subheader(
        f"🏆 次週優先佈局名單 (股價: {int(min_price_input)}~{int(max_price_input)}"
        f" 元，有效門檻: {effective_target_win} 分)"
    )
    df_res = pd.DataFrame(final_results).sort_values(
        by="動能評分", ascending=False
    )
    df_res.index = range(1, len(df_res) + 1)
    st.dataframe(df_res, use_container_width=True)
  else:
    st.warning(
        "⚠️ 目前無標的符合週線強勢突破條件（或因大盤逆風已自動提高門檻）。建議嚴守紀律，保留現金觀望。"
    )
