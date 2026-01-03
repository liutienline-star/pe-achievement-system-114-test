import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import os
import time
import pandas as pd

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年術科 AI 綜評診斷系統", layout="wide", page_icon="🏅")
st.title("🏅 術科 AI 專業評分診斷系統")
st.markdown("##### 結合【現場實測數據】與【AI 影像動作分析】的深度教學工具")

# API 安全金鑰初始化
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # 使用您清單中確認可用的 2.5 Flash 穩定版
    MODEL_ID = "models/gemini-2.5-flash" 
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
        st.error(f"⚠️ 資料讀取失敗，請確認分頁名稱：{e}")
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
        
        # 抓取實測成績數據
        current_record = student_data[student_data["項目"] == sel_test].iloc[0]
        raw_score_val = current_record["成績"]

        st.divider()
        if st.button("🔄 重新整理資料庫"):
            st.cache_data.clear()
            st.rerun()

    # B. 跨表提取指標與常模 (含模糊匹配邏輯)
    try:
        target_test = sel_test.strip()
        match_row = df_criteria[df_criteria["測驗項目"].str.strip() == target_test]
        
        if match_row.empty:
            st.warning(f"💡 項目【{target_test}】尚未在 AI_Criteria 中定義。")
            st.stop()
            
        row_c = match_row.iloc[0]
        
        # 模糊搜尋欄位 (容許 E. 等標題前綴)
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
            st.error("❌ AI_Criteria 標題格式不符，請確保包含 (Data_Unit), (Scoring_Logic) 等英文關鍵字。")
            st.stop()
            
        relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == target_test]
    except Exception as e:
        st.error(f"🚨 資料提取出錯：{e}")
        st.stop()

    # C. 主要介面呈現
    col_info, col_video = st.columns([1, 1.5])
    
    with col_info:
        st.subheader("📊 實測成績摘要")
        st.info(f"**學生**：{sel_name} ({sel_class}班)")
        st.metric(label=f"現場實測 ({unit})", value=f"{raw_score_val} {unit}")
        
        with st.expander("📈 檢視參考常模"):
            st.dataframe(relevant_norms, hide_index=True)
            
        with st.expander("📝 診斷依據指標"):
            st.write(indicators)

    with col_video:
        st.subheader("📹 上傳診斷片段")
        uploaded_v = st.file_uploader("選擇影片 (MP4/MOV)", type=["mp4", "mov"])
        if uploaded_v:
            st.video(uploaded_v)

    # D. 啟動【數據+技術】結合診斷分析
    if st.button(f"🚀 開始【{sel_test}】綜評診斷"):
        if not uploaded_v:
            st.warning("請先上傳影片。")
        else:
            with st.spinner("⏳ AI 正在將數據與動作進行聯網診斷..."):
                try:
                    # 儲存暫存檔
                    temp_path = "temp_diag.mp4"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_v.read())
                    
                    # 上傳至 Gemini
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2)
                        video_file = genai.get_file(video_file.name)
                    
                    # 準備常模資料
                    norms_text = relevant_norms.to_string(index=False)
                    
                    # 核心 Prompt：數據與技術結合
                    full_prompt = f"""
                    你是一位專業的術科教學專家，擅長結合「定量成績」與「定性動作」進行對照分析。
                    目前診斷項目：【{sel_test}】

                    【第一步：內容核對】
                    請判斷影片動作是否為「{sel_test}」。若不符，請直接回覆「⚠️ 項目偵測錯誤」並停止分析。

                    【第二步：數據落點診斷 (定量)】
                    1. 學生實測成績：{raw_score_val} {unit}。
                    2. 參考常模對照：\n{norms_text}\n
                    請分析此成績在常模中的落點與水準。

                    【第三步：動作技術診斷 (定性)】
                    根據以下指標分析影片中的關鍵動作缺失：
                    {indicators}

                    【第四步：綜評診斷 (核心結合)】
                    這是最重要的部分！請將「數據」與「技術」掛鉤：
                    - 分析為什麼學生的技術動作導致了目前的實測數據？(例如：因為揮臂力量不足導致球速慢、數據不佳)。
                    - 診斷動作是否有效率，有無受傷風險。

                    【第五步：產出報告結構】
                    1. 🏆 綜合評等：(給予 數據/技術 的加權總結，1-5顆星)
                    2. 📊 數據診斷：(成績落點與表現分析)
                    3. 🎥 技術診斷：(影片動作關鍵缺失，嚴謹且不美化)
                    4. 💡 突破處方：(根據 {cues} 提供建議。為了提升「數據成績」，「技術動作」具體要改哪裡？)
                    """
                    
                    model = genai.GenerativeModel(MODEL_ID)
                    response = model.generate_content([video_file, full_prompt])
                    
                    st.divider()
                    st.subheader(f"📋 {sel_name} － {sel_test} 綜評診斷報告")
                    st.markdown(response.text)
                    
                    # 清理
                    genai.delete_file(video_file.name)
                    os.remove(temp_path)
                except Exception as e:
                    st.error(f"分析失敗：{e}")
else:
    st.warning("請確認 Google Sheets 連線與分頁名稱。")
