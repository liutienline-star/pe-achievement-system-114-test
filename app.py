# B. 跨表提取指標與常模 (強化報錯版)
    try:
        # 1. 自動修復：將指標表的項目名稱去空格，進行比對
        target_test = sel_test.strip()
        match_row = df_criteria[df_criteria["測驗項目"].str.strip() == target_test]
        
        if match_row.empty:
            st.error(f"❌ 在 AI_Criteria 表中找不到項目：【{target_test}】。請確認名稱是否 100% 相同。")
            st.stop()
            
        row_c = match_row.iloc[0]
        
        # 2. 安全抓取欄位內容 (若欄位名稱不符會給予提示)
        def safe_get(df_row, col_name):
            if col_name in df_row:
                return df_row[col_name]
            else:
                st.error(f"❌ AI_Criteria 表中缺少欄位：【{col_name}】，請務必新增此欄位。")
                st.stop()

        unit = safe_get(row_c, "數據單位 (Data_Unit)")
        logic = safe_get(row_c, "評分權重 (Scoring_Logic)")
        context = safe_get(row_c, "AI 指令脈絡 (AI_Context)")
        indicators = safe_get(row_c, "具體指標 (Indicators)")
        cues = safe_get(row_c, "專業指令與建議 (Cues)")
        
        relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == target_test]
    except Exception as e:
        st.error(f"🚨 系統提取資料時發生錯誤：{e}")
        st.stop()
