import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import re
import os
import time

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年術科 AI 智慧教學平台", layout="wide", page_icon="🏆")

# API 安全金鑰
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "models/gemini-2.5-flash" 
else:
    st.error("❌ 找不到 API_KEY"); st.stop()

# --- 2. 資料庫連線 (參考老師的 ttl=5 設定) ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_sheets():
    try:
        df_c = conn.read(worksheet="AI_Criteria").astype(str)
        df_n = conn.read(worksheet="Norms_Settings").astype(str)
        df_s = conn.read(worksheet="Scores").astype(str)
        df_sl = conn.read(worksheet="Student_List").astype(str)
        try:
            df_h = conn.read(worksheet="Analysis_Results").astype(str)
        except:
            df_h = pd.DataFrame()
        
        # 清理空格
        for df in [df_c, df_n, df_s, df_sl, df_h]:
            if not df.empty:
                df.columns = df.columns.astype(str).str.strip()
        return df_c, df_n, df_s, df_sl, df_h
    except Exception as e:
        st.error(f"資料讀取失敗：{e}"); return None, None, None, None, None

df_criteria, df_norms, df_scores, df_student_list, df_history = load_all_sheets()

# --- 3. 核心判定邏輯 (用於體適能自動換算) ---
def parse_time_to_seconds(time_str):
    try:
        s_val = str(time_str).strip()
        if ":" in s_val:
            parts = s_val.split('.')[0].split(':')
            return int(parts[0]) * 60 + int(parts[1])
        return float(s_val)
    except: return 0

def universal_judge(category, item, gender, age, value, norms_df):
    try:
        mask = (norms_df['測驗類別'] == category) & (norms_df['項目名稱'] == item.strip()) & (norms_df['性別'] == gender)
        filtered = norms_df[mask].copy()
        age_int = int(float(age)) if age else 0
        age_mask = (filtered['年齡'].astype(float).astype(int) == age_int) | (filtered['年齡'].astype(float).astype(int) == 0)
        filtered = filtered[age_mask]
        if filtered.empty: return "待加強"
        v = parse_time_to_seconds(value)
        comp = filtered['比較方式'].iloc[0]
        sorted_norms = filtered.sort_values(by='門檻值', key=lambda x: x.astype(float), ascending=(comp != ">="))
        for _, rule in sorted_norms.iterrows():
            if (comp == ">=" and v >= float(rule['門檻值'])) or (comp == "<=" and v <= float(rule['門檻值'])):
                return rule['判定結果']
    except: pass
    return "待加強"

# --- 4. 側邊欄：學生選擇 (完全依照老師參考程式) ---
if df_scores is not None:
    with st.sidebar:
        st.header("👤 學生與項目選擇")
        df_scores["班級"] = df_scores["班級"].astype(str).str.replace(".0", "", regex=False)
        all_classes = sorted(df_scores["班級"].unique().tolist())
        sel_class = st.selectbox("1. 選擇班級", all_classes)
        
        class_students = df_student_list[df_student_list["班級"].astype(str).str.replace(".0", "") == sel_class]
        sel_name = st.selectbox("2. 選擇學生", class_students["姓名"].unique().tolist())
        
        # 抓取學生基本資料
        stu_info = class_students[class_students["姓名"] == sel_name].iloc[0]
        g_col = next((c for c in df_student_list.columns if "性" in c), "性別")
        sel_gender = str(stu_info[g_col]).strip()
        sel_age = stu_info.get("年齡", "0")
        
        st.info(f"📌 {sel_name} | {sel_gender} | {sel_age}歲")
        st.divider()

# --- 5. 主頁面：功能切換 ---
mode = st.radio("🎯 功能切換", ["一般術科與體適能紀錄", "🚀 AI 智慧診斷教學", "📊 數據報表總覽"], horizontal=True)

# [A. 紀錄功能：包含 114 體適能歷史紀錄]
if mode == "一般術科與體適能紀錄":
    col1, col2 = st.columns(2)
    with col1:
        test_cat = st.selectbox("🗂️ 類別", ["114體適能", "一般術科", "球類", "田徑"])
        items = df_norms[df_norms['測驗類別'] == (test_cat if test_cat != "114體適能" else "體適能")]['項目名稱'].unique()
        sel_item = st.selectbox("📝 測驗項目", list(items) + ["其他"])
    
    with col2:
        if "跑" in sel_item or ":" in sel_item:
            c1, c2 = st.columns(2)
            score_input = f"{c1.number_input('分', 0, 20, 8):02d}:{c2.number_input('秒', 0, 59, 0):02d}.0"
        else:
            score_input = st.text_input("📊 輸入數值", "0")

    final_medal = universal_judge("體適能" if "體適能" in test_cat else "一般術科", sel_item, sel_gender, sel_age, score_input, df_norms)
    st.write(f"📢 判定結果：**{final_medal}**")

    # --- 恢復被省略的近期紀錄對照 (從 Scores 表抓取) ---
    st.subheader(f"🕒 {sel_name} - {sel_item} 歷史紀錄對照")
    history_scores = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_item)]
    if not history_scores.empty:
        st.dataframe(history_scores[["紀錄時間", "成績", "等第/獎牌"]].tail(5), use_container_width=True)
    else:
        st.info("尚無實測紀錄。")

    if st.button("💾 儲存本次成績"):
        new_score = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "班級": sel_class, "姓名": sel_name, "項目": sel_item,
            "成績": score_input, "等第/獎牌": final_medal
        }
        updated_scores = pd.concat([df_scores, pd.DataFrame([new_score])], ignore_index=True)
        conn.update(worksheet="Scores", data=updated_scores)
        st.success("成績已同步至雲端！"); st.cache_data.clear()

# [B. AI 智慧診斷：完全採用老師提供的參考邏輯]
elif mode == "🚀 AI 智慧診斷教學":
    # 選擇已有的項目進行診斷
    available_tests = df_scores[df_scores["姓名"] == sel_name]["項目"].unique().tolist()
    sel_test = st.selectbox("選擇要診斷的項目", available_tests if available_tests else ["請先記錄成績"])
    
    if sel_test in available_tests:
        # 1. 抓取指標 (依據老師參考碼)
        match_row = df_criteria[df_criteria["測驗項目"].str.strip() == sel_test.strip()].iloc[0]
        indicators = match_row.get("Indicators", "")
        cues = match_row.get("Cues", "")
        logic = match_row.get("Logic", "")
        unit = match_row.get("Unit", "")
        relevant_norms = df_norms[df_norms["項目名稱"].str.strip() == sel_test.strip()]
        raw_score_val = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_test)].iloc[-1]["成績"]

        # 2. 介面呈現 (恢復所有被優化的細節)
        col_info, col_video = st.columns([1, 1.5])
        with col_info:
            st.subheader("📊 診斷對照資料")
            st.metric(label=f"最近實測成績 ({unit})", value=f"{raw_score_val}")
            st.markdown(f"**技術指標 (Indicators):**\n{indicators}")
            st.markdown(f"**教學處方 (Cues):**\n{cues}")
            with st.expander("📈 完整常模標準"):
                st.dataframe(relevant_norms, hide_index=True)
            
            st.divider()
            st.subheader("⏳ 診斷歷史紀錄")
            if not df_history.empty:
                past = df_history[(df_history["姓名"] == sel_name) & (df_history["項目"] == sel_test)]
                st.dataframe(past[["時間", "最終得分"]].tail(3), hide_index=True)

        with col_video:
            st.subheader("📹 動作影像分析")
            uploaded_v = st.file_uploader("上傳影片", type=["mp4", "mov"])
            if uploaded_v: st.video(uploaded_v)

            if st.button("🚀 開始 AI 綜合診斷"):
                if not uploaded_v: st.warning("請上傳影片。")
                else:
                    with st.spinner("AI 正在比對資料庫指標進行分析..."):
                        temp_path = "temp.mp4"
                        with open(temp_path, "wb") as f: f.write(uploaded_v.read())
                        video_file = genai.upload_file(path=temp_path)
                        while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                        
                        # 核心 Prompt (維持老師參考碼的高細節格式)
                        full_prompt = f"""
                        你是一位專業的體育術科評分專家。請嚴格參照資料庫內容：
                        【基本資料】姓名：{sel_name}, 登記性別：{sel_gender}, 成績：{raw_score_val} {unit}
                        【技術分析參考指標】：{indicators}
                        【常模判定表】：{relevant_norms.to_string()}
                        【權重計分邏輯】：{logic}
                        【教學處方重點】：{cues}

                        任務：
                        1. **影像核對**：從視覺判斷影片性別，若與登記之『{sel_gender}』不符請首行警示。
                        2. **指標診斷**：對照『技術分析參考指標』，指出學生動作的具體優缺點。
                        3. **處方給予**：根據診斷結果與『教學處方重點』，提供三點建議。
                        """
                        model = genai.GenerativeModel(MODEL_ID)
                        response = model.generate_content([video_file, full_prompt])
                        st.session_state['report'] = response.text
                        st.session_state['done'] = True
                        st.markdown(response.text)
                        genai.delete_file(video_file.name); os.remove(temp_path)

        # 3. 儲存診斷結果
        if st.session_state.get('done'):
            t_note = st.text_area("補充評語")
            if st.button("💾 存檔至 Analysis_Results"):
                new_res = {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "班級": sel_class, "姓名": sel_name, "項目": sel_test,
                    "最終得分": raw_score_val, "AI診斷報告": st.session_state['report'], "老師評語": t_note
                }
                updated_h = pd.concat([df_history, pd.DataFrame([new_res])], ignore_index=True)
                conn.update(worksheet="Analysis_Results", data=updated_h)
                st.success("診斷存檔成功！"); st.cache_data.clear()

# [C. 數據報表總覽]
elif mode == "📊 數據報表總覽":
    st.subheader(f"{sel_class} 班級成績總覽")
    class_data = df_scores[df_scores["班級"] == sel_class]
    st.dataframe(class_data, use_container_width=True)
    st.download_button("📥 下載班級 CSV", class_data.to_csv(index=False).encode('utf-8-sig'), f"{sel_class}.csv")
