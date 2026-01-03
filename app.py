import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import os
import time
import pandas as pd
from datetime import datetime

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年術科 AI 智慧教學平台", layout="wide", page_icon="🏆")
st.title("🏆 術科 AI 智慧教學與管理平台")

# API 安全金鑰
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "models/gemini-2.5-flash" 
else:
    st.error("❌ 找不到 API_KEY"); st.stop()

# --- 2. 資料庫連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5) # 縮短快取時間以便即時看到回寫結果
def load_all_sheets():
    try:
        df_c = conn.read(worksheet="AI_Criteria")
        df_n = conn.read(worksheet="Norms_Settings")
        df_s = conn.read(worksheet="Scores")
        # 嘗試讀取歷史紀錄表，若無則建立空的
        try:
            df_history = conn.read(worksheet="Analysis_Results")
        except:
            df_history = pd.DataFrame()
        
        for df in [df_c, df_n, df_s, df_history]:
            if not df.empty: df.columns = df.columns.str.strip()
        return df_c, df_n, df_s, df_history
    except Exception as e:
        st.error(f"資料讀取失敗：{e}"); return None, None, None, None

df_criteria, df_norms, df_scores, df_history = load_all_sheets()

# --- 項目拍攝指南資料 (第 4 項功能) ---
SHOOTING_GUIDE = {
    "排球": "📷 建議角度：側面 45 度。需捕捉到從『準備撥球』到『擊球後隨揮』的完整動作，確保全身入鏡。",
    "跳遠": "📷 建議角度：正側面。相機高度與腰部同高，需拍到『踏板前三步』、『起跳』與『著地點』。",
    "仰臥起坐": "📷 建議角度：側面 90 度。需看清楚『背部著地』與『手肘碰觸膝蓋』的動作紀錄。",
    "預設": "📷 建議角度：請確保光線充足，動作主體位於畫面中央，背景單純以利 AI 辨識。"
}

# --- 3. 系統核心邏輯 ---
if df_scores is not None:
    # A. 側邊欄與學生選擇
    with st.sidebar:
        st.header("👤 學生與項目選擇")
        df_scores["班級"] = df_scores["班級"].astype(str).str.replace(".0", "", regex=False)
        all_classes = sorted(df_scores["班級"].unique().tolist())
        sel_class = st.selectbox("選擇班級", all_classes)
        
        class_students = df_scores[df_scores["班級"] == sel_class]
        sel_name = st.selectbox("選擇學生", class_students["姓名"].unique().tolist())
        
        student_data = class_students[class_students["姓名"] == sel_name]
        sel_test = st.selectbox("測驗項目", student_data["項目"].unique().tolist())
        
        current_record = student_data[student_data["項目"] == sel_test].iloc[0]
        raw_score_val = current_record["成績"]
        sel_gender = current_record["性別"] if "性別" in current_record else "未註記"

        # --- 第 2 項功能：歷史進步對照 (側邊欄顯示) ---
        st.divider()
        st.subheader("⏳ 歷史紀錄對照")
        if not df_history.empty:
            past_records = df_history[(df_history["姓名"] == sel_name) & (df_history["項目"] == sel_test)]
            if not past_records.empty:
                st.write(f"已有 {len(past_records)} 次紀錄")
                st.dataframe(past_records[["時間", "最終得分"]].tail(3), hide_index=True)
            else:
                st.caption("尚無歷史紀錄")

    # B. 提取權重與指標
    target_test = sel_test.strip()
    match_row = df_criteria[df_criteria["測驗項目"].str.strip() == target_test].iloc[0]
    unit = next((match_row[col] for col in df_criteria.columns if "Unit" in col), "次")
    logic = next((match_row[col] for col in df_criteria.columns if "Logic" in col), "")
    indicators = next((match_row[col] for col in df_criteria.columns if "Indicators" in col), "")
    cues = next((match_row[col] for col in df_criteria.columns if "Cues" in col), "")
    relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == target_test]

    # C. 主要介面呈現
    col_info, col_video = st.columns([1, 1.5])
    
    with col_info:
        st.subheader("📊 數據摘要")
        st.metric(label=f"實測成績 ({unit})", value=f"{raw_score_val}")
        st.write(f"**生理性別**：{sel_gender}")
        with st.expander("⚖️ 當前評分比例"): st.write(logic)

    with col_video:
        st.subheader("📹 影像診斷")
        # --- 第 4 項功能：動態拍攝指南 ---
        guide_text = SHOOTING_GUIDE.get(sel_test[:2], SHOOTING_GUIDE["預設"])
        st.warning(guide_text)
        
        uploaded_v = st.file_uploader("上傳影片 (MP4/MOV)", type=["mp4", "mov"])
        if uploaded_v: st.video(uploaded_v)

    # D. 執行分析
    if st.button(f"🚀 啟動 AI 綜評 (數據+影像)"):
        if not uploaded_v:
            st.warning("請先上傳影片。")
        else:
            with st.spinner("AI 分析中..."):
                try:
                    # 暫存與上傳
                    temp_path = "temp.mp4"
                    with open(temp_path, "wb") as f: f.write(uploaded_v.read())
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                    
                    # 歷史對照提示 (第 2 項)
                    history_context = ""
                    if not df_history.empty and not past_records.empty:
                        last_score = past_records.iloc[-1]['最終得分']
                        history_context = f"該生上次得分為 {last_score}，請簡述其是否有進步。"

                    full_prompt = f"""
                    身分鎖定：{sel_gender} / 項目：{sel_test} / 數據：{raw_score_val} {unit}
                    {history_context}
                    
                    請執行以下任務：
                    1. 偵測性別一致性與項目正確性。
                    2. 計算 0-100 數據分 (參考常模：{relevant_norms.to_string()})。
                    3. 計算 0-100 技術分 (參考指標：{indicators})。
                    4. 依權重【{logic}】算出最終得分。
                    5. 提供診斷報告，格式如下：
                       [SCORE_START]
                       數據分: [數字]
                       技術分: [數字]
                       最終得分: [數字]
                       [SCORE_END]
                       [報告內容...]
                    """
                    model = genai.GenerativeModel(MODEL_ID)
                    response = model.generate_content([video_file, full_prompt])
                    
                    # 暫存結果供回寫使用
                    st.session_state['last_report'] = response.text
                    st.session_state['diag_done'] = True
                    
                    st.divider()
                    st.markdown(response.text)
                    
                    genai.delete_file(video_file.name); os.remove(temp_path)
                except Exception as e: st.error(f"失敗：{e}")

    # --- 第 5 項功能：老師校準區 ---
    if st.session_state.get('diag_done'):
        st.divider()
        st.subheader("👨‍🏫 老師專業校準 (第 5 項功能)")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            teacher_note = st.text_area("給學生的補充評語")
        with col_t2:
            final_adj_score = st.number_input("老師修正最終總分 (若認同 AI 則不需修改)", value=0.0)

        # --- 第 1 項功能：回寫 Google Sheets ---
        if st.button("💾 確認評分並回寫資料庫"):
            with st.spinner("正在儲存資料..."):
                try:
                    # 解析 AI 分數 (從報告中抓取)
                    report_text = st.session_state['last_report']
                    new_row = {
                        "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "班級": sel_class,
                        "姓名": sel_name,
                        "項目": sel_test,
                        "AI診斷報告": report_text,
                        "老師評語": teacher_note,
                        "老師修正總分": final_adj_score if final_adj_score != 0 else "同 AI"
                    }
                    # 實際執行回寫
                    conn.create(worksheet="Analysis_Results", data=pd.DataFrame([new_row]))
                    st.success("✅ 資料已成功同步至 Google Sheets！")
                    st.cache_data.clear() # 強制刷新
                except Exception as e:
                    st.error(f"回寫失敗，請確認分頁 Analysis_Results 是否存在：{e}")

else:
    st.warning("請確認 Google Sheets 連線狀態。")
