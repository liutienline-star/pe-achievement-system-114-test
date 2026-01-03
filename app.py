import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import os
import time
import pandas as pd

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年術科 AI 診斷系統", layout="wide", page_icon="🏅")
st.title("🏅 術科 AI 專業評分診斷系統")
st.markdown("##### 結合現場實測數據與 AI 影像動作分析的專業教學工具")

# API 安全金鑰初始化
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "gemini-1.5-flash" 
else:
    st.error("❌ 找不到 GOOGLE_API_KEY，請在 Streamlit Secrets 中設定。")
    st.stop()

# --- 2. 資料庫連線 (Google Sheets) ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
def load_all_sheets():
    try:
        df_c = conn.read(worksheet="AI_Criteria")
        df_n = conn.read(worksheet="Norms_Settings")
        df_s = conn.read(worksheet="Scores")
        # 清理欄位空格
        for df in [df_c, df_n, df_s]:
            df.columns = df.columns.str.strip()
        return df_c, df_n, df_s
    except Exception as e:
        st.error(f"⚠️ 資料讀取失敗：{e}")
        return None, None, None

df_criteria, df_norms, df_scores = load_all_sheets()

# --- 3. 系統核心邏輯 ---
if df_scores is not None and df_criteria is not None:
    # A. 側邊欄：學生與項目選擇
    with st.sidebar:
        st.header("👤 待診斷名單")
        
        # 班級處理 (轉換為字串避免 .0 問題)
        df_scores["班級"] = df_scores["班級"].astype(str).str.replace(".0", "", regex=False)
        all_classes = sorted(df_scores["班級"].unique().tolist())
        sel_class = st.selectbox("1. 選擇班級", all_classes)
        
        # 學生處理
        class_students = df_scores[df_scores["班級"] == sel_class]
        all_names = class_students["姓名"].unique().tolist()
        sel_name = st.selectbox("2. 選擇學生", all_names)
        
        # 項目處理
        student_data = class_students[class_students["姓名"] == sel_name]
        available_tests = student_data["項目"].unique().tolist()
        sel_test = st.selectbox("3. 選擇測驗項目", available_tests)
        
        # 抓取實測數據
        current_record = student_data[student_data["項目"] == sel_test].iloc[0]
        raw_score_val = current_record["成績"]

        st.divider()
        if st.button("🔄 重新整理資料庫"):
            st.cache_data.clear()
            st.rerun()

    # B. 跨表提取指標與常模 (超強容錯版邏輯)
    try:
        target_test = sel_test.strip()
        match_row = df_criteria[df_criteria["測驗項目"].str.strip() == target_test]
        
        if match_row.empty:
            st.warning(f"💡 項目【{target_test}】尚未在 AI_Criteria 中定義，請檢查名稱是否一致。")
            st.stop()
            
        row_c = match_row.iloc[0]
        
        # 模糊搜尋欄位功能
        def find_col_val(keyword):
            for col in df_criteria.columns:
                if keyword in col: return row_c[col]
            return None

        unit = find_col_val("Data_Unit")
        logic = find_col_val("Scoring_Logic")
        context = find_col_val("AI_Context")
        indicators = find_col_val("Indicators")
        cues = find_col_val("Cues")

        # 檢查必填欄位
        if any(v is None for v in [unit, logic, context]):
            st.error("❌ AI_Criteria 標題格式不符，請確保包含 (Data_Unit), (Scoring_Logic), (AI_Context) 等英文關鍵字。")
            st.stop()
            
        relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == target_test]
    except Exception as e:
        st.error(f"🚨 資料對接出錯：{e}")
        st.stop()

    # C. 主要介面呈現 (資料成功對接後才顯示)
    col_info, col_video = st.columns([1, 1.5])
    
    with col_info:
        st.subheader("📊 實測成績摘要")
        st.info(f"**學生**：{sel_name} ({sel_class}班)")
        st.metric(label=f"現場實測 ({unit})", value=f"{raw_score_val} {unit}")
        with st.expander("📝 檢視評分指標"):
            st.write(f"**具體指標**：\n{indicators}")

    with col_video:
        st.subheader("📹 上傳診斷片段")
        uploaded_v = st.file_uploader("選擇影片 (MP4/MOV)", type=["mp4", "mov"])
        if uploaded_v:
            st.video(uploaded_v)

    # D. 啟動分析
    if st.button(f"🚀 開始【{sel_test}】診斷分析"):
        if not uploaded_v:
            st.warning("請先上傳影片。")
        else:
            with st.spinner("AI 老師正在客觀診斷中..."):
                try:
                    temp_path = "temp_diag.mp4"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_v.read())
                    
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2)
                        video_file = genai.get_file(video_file.name)
                    
                    norms_text = relevant_norms.to_string(index=False)
                    full_prompt = f"{context}\n實測數據：{raw_score_val} {unit}\n常模：{norms_text}\n指標：{indicators}\n權重：{logic}\n建議：{cues}\n請產出平衡且具建設性的三段式回饋。"
                    
                    model = genai.GenerativeModel(MODEL_ID)
                    response = model.generate_content([video_file, full_prompt])
                    
                    st.divider()
                    st.subheader("📋 AI 診斷報告")
                    st.markdown(response.text)
                    
                    genai.delete_file(video_file.name)
                    os.remove(temp_path)
                except Exception as e:
                    st.error(f"分析失敗：{e}")
else:
    st.warning("請確認 Google Sheets 連線與分頁名稱。")
