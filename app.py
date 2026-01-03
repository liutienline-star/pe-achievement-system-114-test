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
    # 建議使用 flash 系列模型，速度最快且對影像理解力強
    MODEL_ID = "gemini-1.5-flash" 
else:
    st.error("❌ 找不到 GOOGLE_API_KEY，請在 Streamlit Secrets 中設定。")
    st.stop()

# --- 2. 資料庫連線 (Google Sheets) ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
def load_all_sheets():
    try:
        # 同時讀取三張核心表單
        df_c = conn.read(worksheet="AI_Criteria")
        df_n = conn.read(worksheet="Norms_Settings")
        df_s = conn.read(worksheet="Scores")
        
        # 清理所有欄位名稱的空白
        for df in [df_c, df_n, df_s]:
            df.columns = df.columns.str.strip()
            
        return df_c, df_n, df_s
    except Exception as e:
        st.error(f"⚠️ 資料讀取失敗，請確認 Sheets 分頁名稱與權限：{e}")
        return None, None, None

df_criteria, df_norms, df_scores = load_all_sheets()

# --- 3. 系統核心邏輯 ---
if df_scores is not None and df_criteria is not None:
    # A. 側邊欄：學生與項目選擇 (從 Scores 表連動)
    with st.sidebar:
        st.header("👤 待診斷名單")
        
        # 1. 選擇班級
        all_classes = df_scores["班級"].astype(str).unique().tolist()
        sel_class = st.selectbox("1. 選擇班級", all_classes)
        
        # 2. 選擇學生
        class_students = df_scores[df_scores["班級"].astype(str) == sel_class]
        all_names = class_students["姓名"].unique().tolist()
        sel_name = st.selectbox("2. 選擇學生", all_names)
        
        # 3. 選擇該學生已測驗的項目
        student_data = class_students[class_students["姓名"] == sel_name]
        available_tests = student_data["項目"].tolist()
        sel_test = st.selectbox("3. 選擇測驗項目", available_tests)
        
        # 4. 自動抓取 Scores 表中的原始成績
        current_record = student_data[student_data["項目"] == sel_test].iloc[0]
        raw_score_val = current_record["成績"]
        # 嘗試抓取性別與年齡 (若表中有)
        std_gender = current_record["性別"] if "性別" in current_record else "未註記"
        std_age = current_record["年齡"] if "年齡" in current_record else "15"

        st.divider()
        if st.button("🔄 重新整理資料庫"):
            st.cache_data.clear()
            st.rerun()

    # B. 跨表提取指標與常模
    try:
        # 從 AI_Criteria 抓取指標與權重
        row_c = df_criteria[df_criteria["測驗項目"] == sel_test].iloc[0]
        unit = row_c["數據單位 (Data_Unit)"]
        logic = row_c["評分權重 (Scoring_Logic)"]
        context = row_c["AI 指令脈絡 (AI_Context)"]
        indicators = row_c["具體指標 (Indicators)"]
        cues = row_c["專業指令與建議 (Cues)"]
        
        # 從 Norms_Settings 抓取符合該項目的常模對照表
        relevant_norms = df_norms[df_norms["項目名稱"] == sel_test]
    except Exception as e:
        st.warning(f"項目【{sel_test}】資料不完整，請檢查 AI_Criteria 分頁。")
        st.stop()

    # C. 主要介面呈現
    col_info, col_video = st.columns([1, 1.5])
    
    with col_info:
        st.subheader("📊 實測成績摘要")
        st.success(f"**學生姓名**：{sel_name} ({std_gender}/{std_age}歲)")
        st.metric(label=f"現場實測 ({unit})", value=f"{raw_score_val} {unit}")
        
        with st.expander("📝 檢視評分權重邏輯"):
            st.caption(logic)
        
        with st.expander("📚 檢視參考常模表"):
            st.dataframe(relevant_norms[["項目名稱", "性別", "年齡", "門檻值", "判定結果", "比較方式"]], hide_index=True)

    with col_video:
        st.subheader("📹 上傳診斷片段")
        st.info("💡 提示：只需錄製 20-30 秒代表性動作即可，無需錄製全程。")
        uploaded_v = st.file_uploader("選擇影片檔案 (MP4, MOV)", type=["mp4", "mov"])
        if uploaded_v:
            st.video(uploaded_v)

    # D. 啟動診斷分析
    if st.button(f"🚀 開始【{sel_test}】綜評診斷"):
        if not uploaded_v:
            st.warning("請上傳影片片段以進行動作分析。")
        else:
            with st.spinner("⏳ AI 正在核對常模、分析動作並平衡評語中..."):
                try:
                    # 影片存檔與上傳至 Gemini
                    temp_path = "temp_diag.mp4"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_v.read())
                    
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2)
                        video_file = genai.get_file(video_file.name)
                    
                    # 準備常模文字
                    norms_text = relevant_norms.to_string(index=False)
                    
                    # 組合最終 Prompt
                    full_prompt = f"""
                    {context}
                    
                    【學生基本資料】：{std_gender}，{std_age}歲。
                    【現場實測數據】：{raw_score_val} {unit}。
                    
                    【官方評分常模數據表】：
                    {norms_text}
                    
                    【動作診斷指標】：
                    {indicators}
                    
                    【評分權重與邏輯】：
                    {logic}
                    
                    【教學建議指令 (Cues)】：
                    {cues}
                    
                    【任務要求】：
                    1. 數據分：根據實測數據對照常模，給出判定結果。
                    2. 技術分：分析影片中的動作是否符合技術指標。
                    3. 綜合評估：根據權重產出總分，並給予「平衡反饋」：
                       - [確認動作]：如實描述做得好的細節。
                       - [關鍵優化]：精確指出需修正的缺失（不美化）。
                       - [訓練處方]：提供具體的修正練習建議。
                    
                    請以 Markdown 格式輸出報告。
                    """
                    
                    model = genai.GenerativeModel(MODEL_ID)
                    response = model.generate_content([video_file, full_prompt])
                    
                    st.divider()
                    st.subheader(f"📋 {sel_name} － {sel_test} 診斷報告")
                    st.markdown(response.text)
                    
                    # 清理暫存檔
                    genai.delete_file(video_file.name)
                    os.remove(temp_path)
                    
                except Exception as e:
                    st.error(f"分析失敗：{e}")

else:
    st.warning("請確認 Google Sheets 連線狀態與分頁名稱是否正確。")
