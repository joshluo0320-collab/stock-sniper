import streamlit as st
import yfinance as yf
import pandas as pd
# ... (前段 get_market_sentiment 與 get_full_market_list 邏輯不變)

# --- 修復：人生合夥人專用建議區 ---
def partner_advice(df_top5, inv_results):
    st.markdown("---")
    st.header("🧠 人生合夥人的戰略建議")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🛡️ 庫藏監控點醒")
        for item in inv_results:
            if item['代號'] == '2337':
                st.write(f"**旺宏 (2337)：** 目前盈虧 {item['即時盈虧']}。利潤極高，**保持冷靜**，不破止盈線不動作。")
            if item['代號'] == '1409':
                st.write(f"**新纖 (1409)：** 波動率低，目前發揮**防禦盾牌**作用，避險價值大於獲利價值。")
                
    with col2:
        st.subheader("🏹 獵殺清單解析")
        if not df_top5.empty:
            top_pick = df_top5.iloc[0]
            st.write(f"**今日首選：{top_pick['代號']}**")
            st.write(f"這支標的綜合勝率達 **{top_pick['綜合勝率']}%**。")
            st.write(f"**能量異動：** {top_pick['能量異動']} 倍。這代表主力已進場，**建議 19 萬現金分批佈局**。")

# (在 UI 執行部分的最後呼叫此函式)
# partner_advice(df_top5, inv_results)
