def execute_sniper_v23_2(df, tid, name, vol_limit, trail_p, max_budget):
    """
    v23.2 重啟版本：加入波動率過濾與能量極大化
    """
    if df.empty or len(df) < 40: return None
    df = df.dropna()
    
    # [1. 價格與預算門檻]
    last_p = round(float(df['Close'].iloc[-1]), 2)
    if last_p > max_budget: return None

    # [2. 波動率過濾 - 踢除牛皮股的核心]
    # 使用 ATR (平均真實波幅) 佔股價比例，低於 1.5% 的直接放生
    tr = pd.concat([df['High'] - df['Low'], 
                    abs(df['High'] - df['Close'].shift(1)), 
                    abs(df['Low'] - df['Close'].shift(1))], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean().iloc[-1]
    volatility_ratio = (atr_14 / last_p) * 100
    if volatility_ratio < 1.5: return None  # <--- 中鋼這類股會在此被無情刷掉

    # [3. 能量與路況計算]
    ma5 = df['Close'].rolling(5).mean()
    ma20 = df['Close'].rolling(20).mean()
    
    # 真正的油門：MACD 斜率 + 價量共振
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    macd = ema_12 - ema_26
    macd_slope = macd.diff().iloc[-1]
    
    avg_v_5 = df['Volume'].tail(5).mean() / 1000
    if avg_v_5 < vol_limit: return None
    v_ratio = (df['Volume'].iloc[-1] / 1000) / avg_v_5

    # [4. 勝率評分重構 - 增加動能權重]
    # 如果價格在 5MA 之上且 MACD 斜率向上，給予重分
    win_5 = 50 if last_p > ma5.iloc[-1] else 0
    win_10 = 50 if macd_slope > 0 else -20
    
    # 突破點偵測
    high_20 = df['High'].rolling(20).max().shift(1).iloc[-1]
    is_break = last_p > high_20
    
    total_score = int((win_5 * 0.4) + (win_10 * 0.6) + (10 if is_break else 0))

    # [5. 撤退線優化]
    # 根據波動率動態調整，不再死守 7%
    dynamic_trail = min(max(trail_p, 3.5), 7.0) 
    withdrawal_line = round(float(df['High'].cummax().iloc[-1] * (1 - dynamic_trail/100)), 2)

    return {
        "名稱": name, "代號": tid, "綜合勝率": total_score,
        "價格": last_p, "波動力": f"{round(volatility_ratio, 2)}%",
        "油門": "🏎️ 加速" if macd_slope > 0 else "🐢 減速",
        "能量": "⛽ 爆量" if v_ratio > 1.5 else "🚗 正常",
        "風險": "⚠️ 隔日沖" if (v_ratio > 3 and (last_p/df['Close'].iloc[-2]-1) > 0.06) else "✅ 穩健",
        "撤退線": withdrawal_line
    }
