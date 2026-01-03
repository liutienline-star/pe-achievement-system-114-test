import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import os
import time
import pandas as pd

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年術科 AI 權重評分系統", layout="wide", page_icon="🏅")
st.title("🏅 術科 AI 專業評分診斷系統")
st.markdown("##### 整合【數據落點】與【影像技術】自動加權計分")

# API 安全金鑰初始化
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "models/gemini-2.5-flash" 
else:
    st.error("❌ 找不到 GOOGLE_API_KEY，請在 Streamlit Secrets 中設定。")
    st.stop()

# --- 2. 資料庫連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
def load_all_sheets():
    try:
        df_c = conn.read(worksheet="AI_Criteria")
        df_n = conn.read(worksheet="Norms_Settings")
        df_s = conn.read(worksheet="Scores")
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
        df_scores["班級"] = df_scores["班級"].astype(str).str.replace(".0", "", regex=False)
        all_classes = sorted(df_scores["班級"].unique().tolist())
        sel_class = st.selectbox("1. 選擇班級", all_classes)
        
        class_students = df_scores[df_scores["班級"] == sel_class]
        all_names = class_students["姓名"].unique().tolist()
        sel_name = st.selectbox("2. 選擇學生", all_names)
        
        student_data = class_students[class_students["姓名"] == sel_name]
        available_tests = student_data["項目"].unique().tolist()
        sel_test = st.selectbox("3. 選擇測驗項目", available_tests)
        
        # 抓取該生該項目的實測數據與性別
        current_record = student_data[student_data["項目"] == sel_test].iloc[0]
        raw_score_val = current_record["成績"]
        sel_gender = current_record["性別"] if "性別" in current_record else "未註記"

        st.divider()
        if st.button("🔄 重新整理資料庫"):
            st.cache_data.clear()
            st.rerun()

    # B. 跨表提取指標與權重邏輯
    try:
        target_test = sel_test.strip()
        match_row = df_criteria[df_criteria["測驗項目"].str.strip() == target_test]
        
        if match_row.empty:
            st.warning(f"💡 項目【{target_test}】尚未在 AI_Criteria 中定義。")
            st.stop()
            
        row_c = match_row.iloc[0]
        
        def find_col_val(keyword):
            for col in df_criteria.columns:
                if keyword in col: return row_c[col]
            return None

        unit = find_col_val("Data_Unit")
        logic = find_col_val("Scoring_Logic") # 權重比例來源
        context = find_col_val("AI_Context")
        indicators = find_col_val("Indicators")
        cues = find_col_val("Cues")

        if any(v is None for v in [unit, logic, context]):
            st.error("❌ AI_Criteria 欄位標題不符，請檢查包含 Data_Unit, Scoring_Logic 等文字。")
            st.stop()
            
        relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == target_test]
    except Exception as e:
        st.error(f"🚨 資料提取出錯：{e}")
        st.stop()

    # C. 主要介面呈現
    col_info, col_video = st.columns([1, 1.5])
    
    with col_info:
        st.subheader("📊 實測成績與性別")
        st.info(f"**學生**：{sel_name} ({sel_gender} / {sel_class}班)")
        st.metric(label=f"現場實測 ({unit})", value=f"{raw_score_val} {unit}")
        
        with st.expander("📈 參考常模標準"):
            st.dataframe(relevant_norms, hide_index=True)
            
        with st.expander("⚖️ 評分權重分配"):
            st.write(logic)

    with col_video:
        st.subheader("📹 上傳診斷片段")
        uploaded_v = st.file_uploader("上傳影片 (MP4/MOV)", type=["mp4", "mov"])
        if uploaded_v:
            st.video(uploaded_v)

    # D. 啟動【加權綜評】診斷分析
    if st.button(f"🚀 開始【{sel_test}】加權綜評診斷"):
        if not uploaded_v:
            st.warning("請先上傳影片。")
        else:
            with st.spinner("⏳ AI 正在計算技術得分並進行性別核對..."):
                try:
                    temp_path = "temp_diag.mp4"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_v.read())
                    
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2)
                        video_file = genai.get_file(video_file.name)
                    
                    norms_text = relevant_norms.to_string(index=False)
                    
                    # 核心 Prompt：鎖定性別並計算加權總分
                    full_prompt = f"""
                    你是一位專業的術科教學與體育評分專家。
                    
                    【受測者基本資料】
                    - 姓名：{sel_name}
                    - 性別：{sel_gender} (請務必依照此性別進行常模比對與技術建議)
                    - 測驗項目：{sel_test}
                    - 實測數據：{raw_score_val} {unit}

                    【第一步：身份核對】
                    1. 檢查影片中人物的性別是否與資料庫紀錄的【{sel_gender}】相符？若不符，請在報告首行發出警示。
                    2. 確認動作是否為 {sel_test}。

                    【第二步：數據分計算 (Data Score)】
                    請參考常模：\n{norms_text}\n
                    根據實測數據 {raw_score_val}，將其轉換為 0-100 分的「數據分」。

                    【第三步：技術分計算 (Technical Score)】
                    根據以下技術指標分析影像中的動作：\n{indicators}\n
                    請給出一個 0-100 分的「技術分」。

                    【第四步：最終總體評分 (Total Score)】
                    請參考您的評分權重邏輯：【{logic}】
                    計算公式：(數據分 × 數據權重) + (技術分 × 技術權重) = 最終得分。

                    【第五步：產出報告結構】
                    1. 🏆 評分總結：
                       - 數據分：[得分]/100
                       - 技術分：[得分]/100
                       - **最終加權得分：[總分]**
                    2. 👤 身份確認：(性別一致性說明)
                    3. 📊 數據診斷：(說明成績在常模中的位置)
                    4. 🎥 技術診斷：(說明影片中為何拿到此技術分，缺失為何)
                    5. 💡 突破處方：(結合 {cues}，為了提高最終得分，應如何優化動作)
                    """
                    
                    model = genai.GenerativeModel(MODEL_ID)
                    response = model.generate_content([video_file, full_prompt])
                    
                    st.divider()
                    st.subheader(f"📋 {sel_name} － {sel_test} 加權診斷報告")
                    st.markdown(response.text)
                    
                    genai.delete_file(video_file.name)
                    os.remove(temp_path)
                except Exception as e:
                    st.error(f"分析失敗：{e}")
else:
    st.warning("請確認 Google Sheets 連線與分頁名稱。")
