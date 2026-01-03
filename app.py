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
        df_sl = conn.read(worksheet="Student_List") # <--- 新增：讀取學生名單
        try:
            df_h = conn.read(worksheet="Analysis_Results")
        except:
            df_h = pd.DataFrame()
        
        # 清理所有欄位名稱的空格
        for df in [df_c, df_n, df_s, df_sl, df_h]:
            if not df.empty:
                df.columns = df.columns.astype(str).str.strip()
        return df_c, df_n, df_s, df_sl, df_h
    except Exception as e:
        st.error(f"資料讀取失敗，請確認工作表名稱：{e}"); return None, None, None, None, None

df_criteria, df_norms, df_scores, df_student_list, df_history = load_all_sheets()

# --- 3. 系統核心邏輯 ---
if df_scores is not None and df_student_list is not None:
    # A. 側邊欄：學生選擇
    with st.sidebar:
        st.header("👤 學生與項目選擇")
        df_scores["班級"] = df_scores["班級"].astype(str).str.replace(".0", "", regex=False)
        all_classes = sorted(df_scores["班級"].unique().tolist())
        sel_class = st.selectbox("1. 選擇班級", all_classes)
        
        class_students = df_scores[df_scores["班級"] == sel_class]
        sel_name = st.selectbox("2. 選擇學生", class_students["姓名"].unique().tolist())
        
        student_records = class_students[class_students["姓名"] == sel_name]
        sel_test = st.selectbox("3. 選擇項目", student_records["項目"].unique().tolist())
        
        # --- 跨表抓取性別邏輯 ---
        student_info = df_student_list[df_student_list["姓名"] == sel_name]
        if not student_info.empty:
            # 尋找包含「性」字的欄位
            g_col = next((c for c in df_student_list.columns if "性" in c), None)
            sel_gender = str(student_info.iloc[0][g_col]).strip() if g_col else "未註記"
        else:
            sel_gender = "未註記"
            st.warning(f"⚠️ 在 Student_List 中找不到【{sel_name}】的資料")

        # 抓取實測數據
        current_record = student_records[student_records["項目"] == sel_test].iloc[0]
        raw_score_val = current_record["成績"]

        st.divider()
        st.subheader("⏳ 歷史紀錄對照")
        if not df_history.empty:
            past = df_history[(df_history["姓名"] == sel_name) & (df_history["項目"] == sel_test)]
            if not past.empty:
                st.dataframe(past[["時間", "最終得分"]].tail(3), hide_index=True)

    # B. 提取 AI 指標
    target_test = sel_test.strip()
    match_rows = df_criteria[df_criteria["測驗項目"].str.strip() == target_test]
    if match_rows.empty:
        st.error(f"❌ 在 AI_Criteria 找不到項目：{target_test}"); st.stop()
    
    match_row = match_rows.iloc[0]
    
    def get_c_val(key):
        col = next((c for c in df_criteria.columns if key in c), None)
        return match_row[col] if col else ""

    unit = get_c_val("Unit")
    logic = get_c_val("Logic")
    indicators = get_c_val("Indicators")
    cues = get_c_val("Cues")
    relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == target_test]

    # C. 介面呈現
    col_info, col_video = st.columns([1, 1.5])
    with col_info:
        st.subheader("📊 診斷對象資料")
        st.metric(label=f"實測成績 ({unit})", value=f"{raw_score_val}")
        st.info(f"姓名：{sel_name}\n\n資料庫性別：**{sel_gender}**")
        with st.expander("📈 參考常模標準"):
            st.dataframe(relevant_norms, hide_index=True)

    with col_video:
        st.subheader("📹 動作影像")
        st.caption("📷 提示：請確保拍攝角度能清楚看見關鍵技術動作。")
        uploaded_v = st.file_uploader("上傳影片", type=["mp4", "mov"])
        if uploaded_v: st.video(uploaded_v)

    # D. AI 分析 (含視覺偵測提示)
    if st.button(f"🚀 開始 AI 綜合診斷"):
        if not uploaded_v:
            st.warning("請先上傳影片。")
        else:
            with st.spinner("AI 正在進行影像分析與性別比對..."):
                try:
                    temp_path = "temp.mp4"
                    with open(temp_path, "wb") as f: f.write(uploaded_v.read())
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                    
                    full_prompt = f"""
                    你是一位專業的體育術科評分專家。
                    
                    【基本資料庫訊息】
                    - 學生姓名：{sel_name}
                    - 登記性別：{sel_gender}
                    - 項目：{sel_test} / 成績：{raw_score_val} {unit}

                    【任務要求】
                    1. **身份與性別核對**：
                       - 請從視覺特徵判斷影片中人物的性別。
                       - 如果影片中的性別與資料庫登記的「{sel_gender}」明顯不同，請在報告最開頭加入警示語：「⚠️ 警示：影像性別特徵與資料庫登記（{sel_gender}）不符，請確認是否上傳正確影片。」
                    
                    2. **專業評分**：
                       - 數據評分參考：{relevant_norms.to_string()}
                       - 技術分析參考：{indicators}
                       - 權重計分邏輯：{logic}
                    
                    3. **教學處方**：參考以下重點：{cues}
                    """
                    model = genai.GenerativeModel(MODEL_ID)
                    response = model.generate_content([video_file, full_prompt])
                    
                    st.session_state['report'] = response.text
                    st.session_state['done'] = True
                    st.divider()
                    st.markdown(response.text)
                    
                    genai.delete_file(video_file.name); os.remove(temp_path)
                except Exception as e: st.error(f"分析出錯：{e}")

    # E. 老師校準與回寫
    if st.session_state.get('done'):
        st.divider()
        st.subheader("👨‍🏫 老師校準與存檔")
        t_note = st.text_area("補充評語")
        t_score = st.text_input("最終修正分數 (選填)")

        if st.button("💾 確認回寫至 Google Sheets"):
            try:
                new_row = {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "班級": sel_class, "姓名": sel_name, "項目": sel_test,
                    "最終得分": t_score if t_score else "見AI報告",
                    "AI診斷報告": st.session_state['report'], "老師評語": t_note
                }
                new_df = pd.DataFrame([new_row])
                try:
                    hist = conn.read(worksheet="Analysis_Results")
                    hist.columns = hist.columns.str.strip()
                    updated = pd.concat([hist, new_df], ignore_index=True)
                except:
                    updated = new_df
                
                conn.update(worksheet="Analysis_Results", data=updated)
                st.success("✅ 資料已成功存入 Analysis_Results！")
                st.cache_data.clear()
            except Exception as e: st.error(f"存檔失敗：{e}")
else:
    st.warning("請確保工作表中有 Scores 與 Student_List 分頁。")
