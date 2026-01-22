# --- 按鈕區塊 (診斷除錯版) ---
button_text = "🚀 啟動嚴格掃描" if strict_mode else "🚀 啟動彈性掃描 (顯示更多)"

if st.button(button_text):
    st.write(f"🔍 開始診斷掃描... 模式：{'嚴格' if strict_mode else '彈性'}")
    
    # 測試連線
    try:
        test_data = yf.download("2330.TW", period="5d", progress=False)
        if test_data.empty:
            st.error("❌ 嚴重錯誤：yfinance 無法抓取數據！可能是 Yahoo 改版或 IP 被鎖。")
            st.stop()
        else:
            st.success(f"✅ 連線測試成功 (台積電數據正常)，開始掃描清單...")
    except Exception as e:
        st.error(f"❌ 連線測試失敗: {e}")
        st.stop()

    progress_bar = st.progress(0)
    status_text = st.empty()
    
    stock_map = dict(zip(stock_list_df['代號'], stock_list_df['名稱']))
    # 為了快速診斷，先只掃描前 20 檔熱門股，節省時間
    tickers = [f"{x}.TW" for x in stock_list_df['代號'].tolist()[:20]] 
    st.info(f"⚡ 診斷模式：僅掃描清單中的前 20 檔股票進行測試...")
    
    total = len(tickers)
    results = []
    error_count = 0
    
    # 改為一次抓一檔，方便抓錯
    for i, ticker in enumerate(tickers):
        progress = (i + 1) / total
        progress_bar.progress(progress)
        status_text.text(f"正在檢查：{ticker} ...")
        
        try:
            data = yf.download(ticker, period="300d", interval="1d", progress=False)
            
            if data.empty:
                st.write(f"⚠️ {ticker}: 無數據 (可能是下市或冷門股)")
                continue

            # 處理 MultiIndex
            if isinstance(data.columns, pd.MultiIndex):
                # 嘗試直接獲取該 ticker 的數據
                if ticker in data.columns.levels[0]:
                    df = data[ticker].copy()
                else:
                    # 如果只有一層 ticker，直接用
                    df = data.copy()
            else:
                df = data.copy()

            df = df.dropna(subset=['Close'])
            
            # 檢查數據長度
            if len(df) < 250:
                # st.write(f"⚠️ {ticker}: 資料不足 250 天 (僅 {len(df)} 天)")
                continue
            
            # --- 這裡直接跳過篩選，強制顯示計算結果，確認計算邏輯無誤 ---
            df = calculate_indicators(df)
            latest = df.iloc[-1]
            win_10d = calculate_win_rate_dynamic(df, look_ahead_days=10, target_pct=0.1)
            
            # 只要能算出來，就加入結果 (不論是否符合勝率)
            results.append({
                "代號": ticker.replace(".TW", ""),
                "名稱": stock_map.get(ticker.replace(".TW", ""), ticker),
                "狀態": "計算成功",
                "收盤價": latest['Close'],
                "10日勝率": win_10d
            })

        except Exception as e:
            error_count += 1
            st.error(f"❌ {ticker} 發生錯誤: {e}")
            # 為了不讓畫面太亂，只顯示前 3 個錯誤
            if error_count > 3:
                st.error("錯誤過多，停止顯示個別錯誤...")
            continue
    
    progress_bar.empty()
    status_text.empty()
    
    if results:
        res_df = pd.DataFrame(results)
        st.success(f"✅ 診斷完成！程式邏輯正常，成功抓取 {len(res_df)} 檔。")
        st.dataframe(res_df)
        st.info("💡 如果這裡有顯示股票，代表程式沒壞，而是之前的『篩選條件』太嚴格導致沒有結果。")
    else:
        st.error("❌ 診斷結束：沒有任何股票能成功計算。請檢查上方的錯誤訊息。")
