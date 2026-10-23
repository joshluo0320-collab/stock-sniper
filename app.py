import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf
from bs4 import BeautifulSoup

# 禁用不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================
# 1. 週動能波段核心邏輯 (Weekly Momentum Swing)
# ============================================
def execute_weekly_sniper(
    df_daily, tid, name, min_price=30.0, max_price=200.0, min_weekly_vol=3000
):
  """平日/假日相容：週線級別動能突破與階梯式風控模型"""
  try:
    if df_daily.empty or len(df_daily) < 60:
      return None

    # 處理 yfinance 多重欄位索引問題
    if isinstance(df_daily.columns, pd.MultiIndex):
      df_daily.columns = df_daily.columns.get_level_values(0)
    df_daily = df_daily.dropna(
        subset=['Open', 'High', 'Low', 'Close', 'Volume']
    )

    if len(df_daily) < 60:
      return None

    # 最新有效交易日與現價 (無論平日盤後或週末，永遠鎖定最新一筆已結算價格)
    latest_trade_date = df_daily.index[-1].strftime('%Y-%m-%d')
    last_p = round(float(df_daily['Close'].iloc[-1]), 1)

    # 價格過濾
    if not (min_price <= last_p <= max_price):
      return None

    # 聚合為週 K 線 (以每週五結算，並清除空週)
    df_weekly = (
        df_daily.resample('W-FRI')
        .agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum',
        })
        .dropna()
    )

    if len(df_weekly) < 15:
      return None

    curr_w = df_weekly.iloc[-1]
    curr_close = float(curr_w['Close'])
    curr_high = float(curr_w['High'])
    curr_low = float(curr_w['Low'])
    curr_open = float(curr_w['Open'])
    curr_vol = float(curr_w['Volume']) / 1000.0  # 轉為張數

    # 成交量門檻過濾 (確保下週進出流動性)
    if curr_vol < min_weekly_vol:
      return None

    # 週線指標：5 週均線 (約月線) 與 10 週均線 (約季線)
    ma5_w = df_weekly['Close'].rolling(5).mean().iloc[-1]
    ma10_w = df_weekly['Close'].rolling(10).mean().iloc[-1]

    # 5 週乖離率 (避免追在過熱末端)
    bias_5w = ((curr_close / ma5_w) - 1) * 100
    if bias_5w > 12.0:
      return None  # 乖離超過 12% 視為過熱阻斷

    # 突破前 4 週高點 (約 20 日真突破)
    prev_4w_high = df_weekly['High'].iloc[-5:-1].max()
    is_break_4w = curr_close > prev_4w_high

    # 週量比 (比對前 4 週平均週量)
    avg_vol_4w = df_weekly['Volume'].iloc[-5:-1].mean() / 1000.0
    vol_ratio = curr_vol / avg_vol_4w if avg_vol_4w > 0 else 0

    # K 線形態結構 (過濾避雷針與出貨長上影線)
    total_range = curr_high - curr_low
    upper_shadow = curr_high - max(curr_close, curr_open)
    body = abs(curr_close - curr_open)

    is_bullish = curr_close >= curr_open
    is_clean_candle = (
        (upper_shadow / total_range < 0.35) if total_range > 0 else True
    )

    # 動能核心條件門檻
    if not (
        curr_close > ma5_w
        and curr_close > ma10_w
        and is_break_4w
        and vol_ratio >= 1.3
        and is_bullish
        and is_clean_candle
    ):
      return None

    # 動能評分系統 (0 ~ 100 分)
    score = 50
    score += 20 if vol_ratio >= 1.8 else 10
    high_12w = df_weekly['High'].iloc[-13:-1].max()
    is_super_break = curr_close > high_12w
    score += 15 if is_super_break else 0
    score += 15 if (body / total_range >= 0.6 if total_range > 0 else False) else 5
    win_score = min(score, 100)

    # 階梯式風控價位試算
    entry_ref = last_p
    # 初始硬停損：本週低點 或 進場價 -4.5% (取高者，守住下檔風險)
    risk_floor = max(curr_low, round(entry_ref * 0.955, 1))
    hard_stop_loss = round(risk_floor, 1)

    # 保本與目標價位
    breakeven_trigger = round(entry_ref * 1.05, 1)  # 漲幅達 5% 啟動保本
    target_lock_p = round(entry_ref * 1.08, 1)  # 漲幅達 8% 獲利收網

    # 特例續抱判定
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
# 2. 名單抓取工具 (上市與上櫃股票代號)
# ============================================
@st.cache_data(ttl=86400)
def get_market_map():
  tickers, names_map = [], {}
  urls = [
      'https://isin.twse.com.tw/isin/C_public.jsp?strMode=2',  # 上市
      'https://isin.twse.com.tw/isin/C_public.jsp?strMode=4',  # 上櫃
  ]
  for url in urls:
    try:
      res = requests.get(url, verify=False, timeout=10)
      res.encoding = 'big5'
      soup = BeautifulSoup(res.text, 'lxml')
      for row in soup.find_all('tr'):
        tds = row.find_all('td')
        if len(tds) > 0:
          raw = tds[0].text.strip().split()
          if len(raw) >= 2 and len(raw[0]) == 4 and raw[0].isdigit():
            suffix = '.TW' if 'strMode=2' in url else '.TWO'
            tickers.append(f'{raw[0]}{suffix}')
            names_map[raw[0]] = raw[1]
    except Exception:
      continue
  return tickers, names_map


# ============================================
# 3. Streamlit UI 戰略介面
# ============================================
st.set_page_config(page_title='週動能獵殺系統 v24.1', layout='wide')

st.sidebar.header('🕹️ 週輪動控制台 v24.1')
target_win = st.sidebar.slider('🎯 動能評分門檻', 50, 95, 70, step=5)
min_weekly_vol_input = st.sidebar.slider(
    '🌊 週成交量門檻 (張)', 1000, 10000, 3000, step=500
)

st.sidebar.markdown('---')
st.sidebar.subheader('💰 股價自選區間')
min_price_input = st.sidebar.number_input('最低股價 (元)', value=30.0, step=5.0)
max_price_input = st.sidebar.number_input(
    '最高股價 (元)', value=180.0, step=10.0
)

st.sidebar.markdown('---')
inventory_input = st.sidebar.text_area('📋 庫存監控 (代號,成本)', value='2337,34')

st.title('🏹 2026 週級別動能輪動系統 (平日/週末全相容版)')
st.caption(
    '💡 核心紀律：週末選股 ➔ 週一開盤進場 ➔ 週間智慧停損/保本 ➔ 週五 13:00'
    ' 無條件清倉變現（免受週末利空影響）'
)

# --- A. 庫存檢視模組 ---
st.subheader('📊 庫藏動態與週線階梯防守')
if st.button('🔄 刷新庫存狀態'):
  inv_list = [l.split(',') for l in inventory_input.split('\n') if ',' in l]
  inv_data = []
  for tid, cost in inv_list:
    tid = tid.strip()
    df = yf.download(f'{tid}.TW', period='1y', progress=False)
    if df.empty:
      df = yf.download(f'{tid}.TWO', period='1y', progress=False)

    if not df.empty:
      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
      curr_price = float(df['Close'].iloc[-1])
      cost_val = float(cost)
      p_l = (curr_price / cost_val - 1) * 100

      # 試算當前防守基準 (以近 4 週低點或成本 -4.5% 防守)
      recent_low_4w = df['Low'].tail(20).min()
      stop_line = max(round(cost_val * 0.955, 1), round(recent_low_4w, 1))

      inv_data.append({
          '代號': tid,
          '現價': curr_price,
          '成本': cost_val,
          '當前盈虧': f'{round(p_l, 1)}%',
          '初始/動態防守線': stop_line,
          '狀態': '✅ 抱牢中' if curr_price > stop_line else '⚠️ 觸及防守線',
          '保本達標': (
              '🎯 已可設定保本單' if curr_price >= cost_val * 1.05 else '⏳ 觀察中'
          ),
      })

  if inv_data:
    st.table(pd.DataFrame(inv_data))
  else:
    st.info('請在庫存監控輸入正確格式，如：2337,34')

st.markdown('---')

# --- B. 全市場週動能掃描模組 ---
if st.button('🔴 啟動全市場週動能掃描 (全台股)', type='primary'):
  final_results = []
  tickers, names_map = get_market_map()

  with st.status(
      f'📡 正在掃描台股全標的週線動能... 總計檔數：{len(tickers)} 檔',
      expanded=True,
  ) as status:
    pb = st.progress(0)
    chunk_size = 60

    for i in range(0, len(tickers), chunk_size):
      chunk = tickers[i : i + chunk_size]
      pb.progress(min((i + chunk_size) / len(tickers), 1.0))
      try:
        # 下載 1 年資料以聚合週線
        data = yf.download(
            chunk, period='1y', group_by='ticker', progress=False
        )
        for t in chunk:
          tid = t.split('.')[0]
          df_stock = data[t] if len(chunk) > 1 else data

          res = execute_weekly_sniper(
              df_stock,
              tid,
              names_map.get(tid, tid),
              min_price=min_price_input,
              max_price=max_price_input,
              min_weekly_vol=min_weekly_vol_input,
          )

          if res and res['動能評分'] >= target_win:
            final_results.append(res)
      except Exception:
        continue

    status.update(label='🎯 全市場週動能掃描完成！', state='complete')

  if final_results:
    st.subheader(
        f'🏆 次週優先佈局名單 (股價: {int(min_price_input)}~{int(max_price_input)}'
        f' 元，評分門檻: {target_win} 分)'
    )
    df_res = pd.DataFrame(final_results).sort_values(
        by='動能評分', ascending=False
    )
    df_res.index = range(1, len(df_res) + 1)
    st.dataframe(df_res, use_container_width=True)
  else:
    st.warning(
        '⚠️'
        ' 目前無標的符合週線強勢突破條件。在多頭力道不足時，建議保留現金觀望。'
    )
