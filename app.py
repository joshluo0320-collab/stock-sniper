import streamlit as st
import yfinance as yf
import pandas as pd
# ... (省略名單抓取與基礎設定)

def advanced_sniper_v22(df, tid, name, vol_gate, trail_p, max_budget):
    # ... (基礎技術指標計算)
    
    # [新增：隔日沖陷阱偵測]
    vol_5d_avg = df['Volume'].tail(5).mean()
    today_vol = df['Volume'].iloc[-1]
    today_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) * 100
    is_day_trade_trap = today_vol > (vol_5d_avg * 2.5) and today_ret > 7
    
    # [新增：法人動態模擬 (需付費數據，此處以價量慣性模擬)]
    # 當 10 日收盤價持續站穩且量能溫和放大，模擬為法人佈局
    institutional_support = (df['Close'].tail(10) > df['Close'].rolling(20).mean().tail(10)).all()

    # 綜合勝率調整
    score = 50 # 基礎分
    score += 20 if institutional_support else -10 # 法人護盤加分
    score -= 15 if is_day_trade_trap else 0 # 隔日沖陷阱扣分
    
    return {
        "名稱": name, "代號": tid, "收盤": last_p,
        "綜合勝率": int(min(98, score)),
        "戰略屬性": "🏛️ 法人盤" if institutional_support else "🏹 散戶/短線盤",
        "風險預警": "⚠️ 隔日沖出貨風險" if is_day_trade_trap else "✅ 籌碼相對穩定",
        "隔日進場區": f"{round(last_p * 0.98, 2)}~{round(last_p * 0.995, 2)}",
        "合夥人解析": "此標的能量爆滿但有隔日沖嫌疑，明日開盤若未站穩今日收盤價，請勿扣板機。" if is_day_trade_trap else "趨勢穩健，適合 19 萬現金分批佈局。"
    }

# UI 顯示部分將「戰略屬性」與「風險預警」獨立出來供你一眼掃描
