# --- A. 庫存檢視模組 (週輪動戰術看板升級版) ---
st.subheader("📊 庫存動態與週結算戰情室")

# 支援格式：代號, 成本, 買進日期(可選，如 2026-10-19)
inv_lines = [
    l.strip()
    for l in inventory_input.split('\n')
    if ',' in l and l.strip() != ''
]

if inv_lines:
  inv_data = []
  today_date = pd.Timestamp.now()
  is_friday = today_date.weekday() == 4  # 4 代表星期五

  for line in inv_lines:
    parts = [p.strip() for p in line.split(',')]
    tid = parts[0]
    cost_val = float(parts[1])
    buy_date = parts[2] if len(parts) >= 3 else '未指定'

    # 下載日線資料計算最新現價與均線
    df = yf.download(f'{tid}.TW', period='6mo', progress=False)
    if df.empty:
      df = yf.download(f'{tid}.TWO', period='6mo', progress=False)

    if not df.empty:
      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      curr_p = round(float(df['Close'].iloc[-1]), 1)
      p_l = round((curr_p / cost_val - 1) * 100, 2)

      # 階梯防守點位計算
      hard_stop = round(cost_val * 0.955, 1)  # 初始 -4.5% 硬停損
      be_trigger = round(cost_val * 1.05, 1)  # +5% 保本觸發點
      target_p = round(cost_val * 1.08, 1)  # +8% 目標獲利點

      # 狀態邏輯判斷
      if curr_p <= hard_stop:
        action = '🚨 觸及停損 (立即出場)'
        color_tag = '🔴 停損'
      elif is_friday:
        action = (
            '⏳ 週五結算日 (13:00 清倉變現)'
            if curr_p < target_p
            else '🚀 達標！收網獲利'
        )
        color_tag = '🟡 結算'
      elif curr_p >= be_trigger:
        action = '🛡️ 已達 +5%，券商掛成本價保本'
        color_tag = '🟢 保本'
      else:
        action = '📈 正常抱牢中'
        color_tag = '⚪ 持續'

      inv_data.append({
          '代號': tid,
          '買進日': buy_date,
          '成本價': cost_val,
          '當前現價': curr_p,
          '盈虧幅度': f'{p_l}%',
          '初始停損(-4.5%)': hard_stop,
          '保本線(+5%)': be_trigger,
          '目標線(+8%)': target_p,
          '戰術燈號': color_tag,
          '當前執行指引': action,
          'raw_p_l': p_l,
      })

  if inv_data:
    df_inv = pd.DataFrame(inv_data)

    # 頂部儀表板卡片
    col1, col2, col3, col4 = st.columns(4)
    avg_return = df_inv['raw_p_l'].mean()
    col1.metric('總持倉檔數', f"{len(df_inv)} 檔")
    col2.metric('整體平均盈虧', f'{round(avg_return, 2)}%')
    col3.metric('最高獲利標的', f"{df_inv['raw_p_l'].max()}%")
    alert_count = len(
        df_inv[df_inv['戰術燈號'].isin(['🔴 停損', '🟡 結算'])]
    )
    col4.metric('需即時處理', f'{alert_count} 檔')

    # 呈現格式化表格
    display_df = df_inv.drop(columns=['raw_p_l'])
    display_df.index = range(1, len(display_df) + 1)
    st.dataframe(display_df, use_container_width=True)
else:
  st.info('💡 請在側邊欄庫存監控輸入持倉，格式範例：`2337, 70, 2026-10-19`')
