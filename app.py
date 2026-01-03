import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import os
import time
import pandas as pd

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年術科 AI 診斷系統", layout="wide", page_icon="🏅")
st.title("🏅 術科 AI 專業評分診斷系統")
st.markdown("##### 整合實測數據與影像分析的專業教學工具")

# API 安全金鑰初始化 (使用 2026 最新穩定版模型)
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # 根據您的模型清單，使用 2.5 Flash 最為穩定快速
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
        # 清理所有欄位名稱的空格
        for df in [df_c, df_n, df_s]:
            df.columns = df.columns.str.strip()
        return df_c, df_n, df_s
    except Exception as e:
        st.error(f"⚠️ 資料讀取失敗，請確認 Sheets 分頁名稱與權限：{e}")
        return None, None, None

df_criteria, df_norms, df_scores = load_all_sheets()

# --- 3. 系統核心邏輯 ---
if df_scores is not None and df_criteria is not None:
    # A. 側邊欄：學生與項目選擇
    with st.sidebar:
        st.header("👤 待診斷名單")
        
        # 班級處理：防止出現 809.0 這種格式
        df_scores["班級"] = df_scores["班級"].astype(str).str.replace(".0", "", regex=False)
        all_classes = sorted(df_scores["班級"].unique().tolist())
        sel_class = st.selectbox("1. 選擇班級", all_classes)
        
        # 學生處理
        class_students = df_scores[df_scores["班級"] == sel_class]
        all_names = class_students["姓名"].unique().tolist()
        sel_name = st.selectbox("2. 選擇學生", all_names)
        
        # 項目處理 (自動從 Scores 表抓取該生已有的項目)
        student_data = class_students[class_students["姓名"] == sel_name]
        available_tests = student_data["項目"].unique().tolist()
        sel_test = st.selectbox("3. 選擇測驗項目", available_tests)
        
        # 抓取該生該項目的實測數字
        current_record = student_data[student_data["項目"] == sel_test].iloc[0]
        raw_score_val = current_record["成績"]

        st.divider()
        if st.button("🔄 重新整理資料庫"):
            st.cache_data.clear()
            st.rerun()

    # B. 跨表提取指標與常模 (含模糊匹配邏輯)
    try:
        # 1. 項目比對 (去空格)
        target_test = sel_test.strip()
        match_row = df_criteria[df_criteria["測驗項目"].str.strip() == target_test]
        
        if match_row.empty:
            st.warning(f"💡 項目【{target_test}】在 AI_Criteria 表中找不到完全相符的名稱。")
            st.stop()
            
        row_c = match_row.iloc[0]
        
        # 2. 欄位抓取 (只要標題包含關鍵字即可，容許 E. 等前綴)
        def find_val(keyword):
            for col in df_criteria.columns:
                if keyword in col: return row_c[col]
            return None

        unit = find_val("Data_Unit")
        logic = find_val("Scoring_Logic")
        context = find_val("AI_Context")
        indicators = find_val("Indicators")
        cues = find_val("Cues")

        # 檢查關鍵資料是否齊全
        if any(v is None for v in [unit, logic, context]):
            st.error("❌ AI_Criteria 表格欄位名稱不符，請確保包含 (Data_Unit), (Scoring_Logic), (AI_Context) 等關鍵字。")
            st.stop()
            
        relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == target_test]
    except Exception as e:
        st.error(f"🚨 資料對接出錯：{e}")
        st.stop()

    # C. 主要介面呈現
    col_info, col_video = st.columns([1, 1.5])
    
    with col_info:
        st.subheader("📊 實測成績摘要")
        st.info(f"**學生**：{sel_name} ({sel_class}班)")
        st.metric(label=f"現場實測 ({unit})", value=f"{raw_score_val} {unit}")
        
        with st.expander("📝 檢視評分指標細節"):
            st.markdown(f"**具體指標**：\n{indicators}")
            st.markdown(f"**建議指令**：\n{cues}")

    with col_video:
        st.subheader("📹 上傳診斷片段")
        uploaded_v = st.file_uploader("請上傳 20-30 秒代表性動作 (MP4/MOV)", type=["mp4", "mov"])
        if uploaded_v:
            st.video(uploaded_v)

    # D. 啟動診斷分析 (含防幻覺邏輯)
    if st.button(f"🚀 開始【{sel_test}】綜評診斷"):
        if not uploaded_v:
            st.warning("請先上傳影片片段。")
        else:
            with st.spinner("⏳ AI 正在核對影片內容並進行專業分析..."):
                try:
                    temp_path = "temp_diag.mp4"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_v.read())
                    
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2)
                        video_file = genai.get_file(video_file.name)
                    
                    # 準備常模字串
                    norms_text = relevant_norms.to_string(index=False)
                    
                    # 組合嚴謹的 Prompt
                    full_prompt = f"""
                    你是一位極其嚴謹且誠實的術科教學專家。目前要診斷的項目是：【{sel_test}】。

                    【第一步：內容核對】
                    請先觀看影片，判斷影片中的動作是否為「{sel_test}」。
                    - 如果影片內容「不是」{sel_test}，請直接回覆：「⚠️ 影片內容偵測錯誤：偵測到影片內容非目標項目 [{sel_test}]，請重新上傳正確影片。」且不要進行後續診斷。
                    - 嚴禁強行解釋或編造不實的報告。

                    【第二步：專業診斷】(僅在內容正確時執行)
                    {context}

                    學生實測數據：{raw_score_val} {unit}
                    參考常模：
                    {norms_text}

                    具體技術指標：
                    {indicators}

                    評分與平衡指令邏輯：
                    {logic}

                    教學建議 (Cues)：
                    {cues}

                    任務要求：
                    1. 結合實測數據與動作分析，給出客觀評價。
                    2. 產出三段式報告：[確認動作]、[關鍵優化]（不美化缺失）、[訓練處方]。
                    """
                    
                    model = genai.GenerativeModel(MODEL_ID)
                    response = model.generate_content([video_file, full_prompt])
                    
                    st.divider()
                    st.subheader(f"📋 {sel_name} － {sel_test} 診斷報告")
                    st.markdown(response.text)
                    
                    # 清理暫存
                    genai.delete_file(video_file.name)
                    os.remove(temp_path)
                    
                except Exception as e:
                    st.error(f"分析失敗，錯誤訊息：{e}")

else:
    st.warning("系統尚未連線。請確認 Google Sheets 分頁名稱是否為 Scores, AI_Criteria, Norms_Settings。")
