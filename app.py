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

@st.cache_data(ttl=5)
def load_all_sheets():
    try:
        df_c = conn.read(worksheet="AI_Criteria")
        df_n = conn.read(worksheet="Norms_Settings")
        df_s = conn.read(worksheet="Scores")
        # 讀取歷史紀錄表 (第 1 項功能所需)
        try:
            df_history = conn.read(worksheet="Analysis_Results")
        except:
            df_history = pd.DataFrame()
        
        for df in [df_c, df_n, df_s, df_history]:
            if not df.empty:
                df.columns = df.columns.str.strip()
        return df_c, df_n, df_s, df_history
    except Exception as e:
        st.error(f"資料讀取失敗，請確認分頁名稱是否正確：{e}"); return None, None, None, None

df_criteria, df_norms, df_scores, df_history = load_all_sheets()

# --- 項目拍攝指南 (第 4 項功能) ---
SHOOTING_GUIDE = {
    "排球": "📷 建議角度：側面 45 度。需捕捉到從『準備撥球』到『擊球後隨揮』的完整動作。",
    "跳遠": "📷 建議角度：正側面。相機高度與腰部同高，需拍到『起跳』與『落點』。",
    "預設": "📷 建議角度：請確保光線充足，動作主體位於畫面中央。"
}

# --- 3. 系統核心邏輯 ---
if df_scores is not None and df_criteria is not None:
    # A. 側邊欄：學生選擇
    with st.sidebar:
        st.header("👤 學生與項目選擇")
        df_scores["班級"] = df_scores["班級"].astype(str).str.replace(".0", "", regex=False)
        all_classes = sorted(df_scores["班級"].unique().tolist())
        sel_class = st.selectbox("1. 選擇班級", all_classes)
        
        class_students = df_scores[df_scores["班級"] == sel_class]
        sel_name = st.selectbox("2. 選擇學生", class_students["姓名"].unique().tolist())
        
        student_data = class_students[class_students["姓名"] == sel_name]
        sel_test = st.selectbox("3. 選擇項目", student_data["項目"].unique().tolist())
        
        current_record = student_data[student_data["項目"] == sel_test].iloc[0]
        raw_score_val = current_record["成績"]
        sel_gender = current_record["性別"] if "性別" in current_record else "未註記"

        # --- 第 2 項功能：歷史紀錄查詢 ---
        st.divider()
        st.subheader("⏳ 歷史進步對照")
        if not df_history.empty:
            past = df_history[(df_history["姓名"] == sel_name) & (df_history["項目"] == sel_test)]
            if not past.empty:
                st.dataframe(past[["時間", "最終得分"]].tail(3), hide_index=True)
            else:
                st.caption("尚無歷史數據")

    # B. 提取 AI 指標 (修復 IndexError 之核心)
    target_test = sel_test.strip()
    # 這裡加入搜尋檢查，防止 iloc[0] 當機
    matching_rows = df_criteria[df_criteria["測驗項目"].str.strip() == target_test]
    
    if matching_rows.empty:
        st.error(f"❌ 找不到項目：【{target_test}】")
        st.warning(f"請檢查 AI_Criteria 工作表，目前的項目名稱有：{df_criteria['測驗項目'].tolist()}")
        st.stop()
    
    match_row = matching_rows.iloc[0]
    
    # 維持您的數據對接，不進行簡化
    unit = next((match_row[col] for col in df_criteria.columns if "Unit" in col), "")
    logic = next((match_row[col] for col in df_criteria.columns if "Logic" in col), "")
    indicators = next((match_row[col] for col in df_criteria.columns if "Indicators" in col), "")
    cues = next((match_row[col] for col in df_criteria.columns if "Cues" in col), "")
    relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == target_test]

    # C. 介面呈現
    col_info, col_video = st.columns([1, 1.5])
    with col_info:
        st.subheader("📊 數據摘要")
        st.metric(label=f"實測成績 ({unit})", value=f"{raw_score_val}")
        st.info(f"受測性別：{sel_gender}")
        with st.expander("📈 查看參考常模"):
            st.dataframe(relevant_norms, hide_index=True)

    with col_video:
        st.subheader("📹 影像診斷")
        # 第 4 項：拍攝指南
        st.warning(SHOOTING_GUIDE.get(sel_test[:2], SHOOTING_GUIDE["預設"]))
        uploaded_v = st.file_uploader("上傳動作影片", type=["mp4", "mov"])
        if uploaded_v: st.video(uploaded_v)

    # D. 分析與回寫
    if st.button(f"🚀 啟動 AI 綜評"):
        if not uploaded_v:
            st.warning("請先上傳影片。")
        else:
            with st.spinner("AI 診斷中..."):
                try:
                    temp_path = "temp.mp4"
                    with open(temp_path, "wb") as f: f.write(uploaded_v.read())
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                    
                    full_prompt = f"""
                    診斷對象：{sel_gender} / 項目：{sel_test} / 數據：{raw_score_val} {unit}
                    常模參考：{relevant_norms.to_string()}
                    技術指標：{indicators}
                    權重邏輯：{logic}
                    教學指令：{cues}
                    
                    任務：
                    1. 核對性別與項目是否正確。
                    2. 計算數據分、技術分，並依權重計算最終總分。
                    3. 提供三段式報告：[數據落點]、[動作技術缺失(嚴謹)]、[突破處方]。
                    """
                    model = genai.GenerativeModel(MODEL_ID)
                    response = model.generate_content([video_file, full_prompt])
                    
                    st.session_state['report'] = response.text
                    st.session_state['done'] = True
                    st.markdown(response.text)
                    
                    genai.delete_file(video_file.name); os.remove(temp_path)
                except Exception as e: st.error(f"分析失敗：{e}")

    # --- 第 5 項：老師校準區 ---
    if st.session_state.get('done'):
        st.divider()
        st.subheader("👨‍🏫 老師專業校準")
        t_note = st.text_area("給學生的額外評語")
        t_score = st.text_input("老師修正總分 (如不修正請留空)")

        # --- 第 1 項：回寫功能 ---
        if st.button("💾 確認並回寫至 Google Sheets"):
            try:
                new_data = pd.DataFrame([{
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "班級": sel_class, "姓名": sel_name, "項目": sel_test,
                    "最終得分": t_score if t_score else "見AI報告",
                    "AI診斷報告": st.session_state['report'],
                    "老師評語": t_note
                }])
                conn.create(worksheet="Analysis_Results", data=new_data)
                st.success("✅ 數據已存入 Analysis_Results 分頁！")
                st.cache_data.clear()
            except Exception as e: st.error(f"回寫失敗：{e}")
else:
    st.warning("請確認 Google Sheets 工作表連線。")
