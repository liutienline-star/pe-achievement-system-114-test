import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import re
import os
import time

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年度體育成績管理系統", layout="wide", page_icon="🏆")

# --- 2. 登入權限管理 (完全保留您的核心安全邏輯) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True
    st.title("🔒 體育成績管理系統 - 登入")
    col1, _ = st.columns([1, 2])
    with col1:
        u = st.text_input("👤 管理員帳號", value="")
        p = st.text_input("🔑 密碼", type="password")
        if st.button("🚀 確認登入"):
            if u == "tienline" and p == "641101":
                st.session_state["password_correct"] = True
                st.rerun()
            else: st.error("🚫 帳號或密碼錯誤")
    return False

if not check_password(): st.stop()

# --- 3. AI 模型初始化 (使用您指定的 2.5 版本) ---
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "models/gemini-2.5-flash" 
else:
    st.error("❌ 找不到 API_KEY"); st.stop()

# --- 4. 資料連線與快取 (整合所有分頁) ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_data():
    try:
        # 同時讀取管理系統與 AI 分析所需的所有分頁
        s_df = conn.read(worksheet="Scores", ttl="0s").astype(str)
        sl_df = conn.read(worksheet="Student_List", ttl="0s").astype(str)
        n_df = conn.read(worksheet="Norms_Settings", ttl="0s").astype(str)
        c_df = conn.read(worksheet="AI_Criteria", ttl="0s").astype(str)
        try:
            h_df = conn.read(worksheet="Analysis_Results", ttl="0s").astype(str)
        except:
            h_df = pd.DataFrame()
            
        # 清理欄位名稱空格 (您的核心清理邏輯)
        for df in [s_df, sl_df, n_df, c_df, h_df]:
            if not df.empty: df.columns = df.columns.astype(str).str.strip()
        return s_df, sl_df, n_df, c_df, h_df
    except Exception as e:
        st.error(f"資料讀取失敗：{e}"); st.stop()

scores_df, student_list, norms_settings_df, ai_criteria_df, ai_history = load_all_data()

# --- 5. 核心判定引擎 (完全恢復您的精密運算邏輯) ---
def clean_numeric_string(val):
    if pd.isna(val) or val == 'nan' or val == "": return ""
    s = str(val).strip()
    return str(int(float(s))) if re.match(r'^\d+\.0$', s) else s

def parse_time_to_seconds(time_str):
    try:
        s_val = str(time_str).strip()
        if ":" in s_val:
            main = s_val.split('.')[0]
            parts = main.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        return float(s_val)
    except: return 0

def universal_judge(category, item, gender, age, value, norms_df):
    try:
        mask = (norms_df['測驗類別'] == category) & \
               (norms_df['項目名稱'] == item.strip()) & \
               (norms_df['性別'] == gender)
        filtered = norms_df[mask].copy()
        if filtered.empty: return "查無常模"

        age_int = int(float(age)) if age else 0
        age_mask = (filtered['年齡'].astype(float).astype(int) == age_int) | (filtered['年齡'].astype(float).astype(int) == 0)
        filtered = filtered[age_mask]
        if filtered.empty: return "待加強"

        v = parse_time_to_seconds(value)
        comp_method = filtered['比較方式'].iloc[0]

        if comp_method == ">=":
            sorted_norms = filtered.sort_values(by='門檻值', key=lambda x: x.astype(float), ascending=False)
            for _, rule in sorted_norms.iterrows():
                if v >= float(rule['門檻值']): return rule['判定結果']
        else:
            sorted_norms = filtered.sort_values(by='門檻值', key=lambda x: x.astype(float), ascending=True)
            for _, rule in sorted_norms.iterrows():
                if v <= float(rule['門檻值']): return rule['判定結果']
    except: pass
    return "待加強"

# --- 6. 側邊欄與資料清理 ---
scores_df = scores_df.map(clean_numeric_string)
student_list = student_list.map(clean_numeric_string)

with st.sidebar:
    st.header("👤 學生與項目選擇")
    if not student_list.empty:
        cl_list = sorted(student_list['班級'].unique())
        sel_class = st.selectbox("🏫 選擇班級", cl_list)
        stu_df = student_list[student_list['班級'] == sel_class]
        no_list = stu_df['座號'].sort_values(key=lambda x: pd.to_numeric(x, errors='coerce')).unique()
        sel_no = st.selectbox("🔢 選擇座號", no_list)
        stu = stu_df[stu_df['座號'] == sel_no].iloc[0]
        
        # 自動跨表抓取性別與年齡
        g_col = next((c for c in student_list.columns if "性" in c), "性別")
        sel_gender = str(stu[g_col]).strip()
        st.info(f"📌 {stu['姓名']} | {sel_gender} | {stu['年齡']}歲")
    else: st.stop()

# --- 7. 主介面：功能導航 ---
st.title("🏆 114學年度體育成績管理與 AI 智慧平台")
mode = st.radio("🎯 功能切換", ["一般術科測驗", "114年體適能", "🚀 AI 智慧診斷教學", "📊 數據報表查詢"], horizontal=True)

# [A. 一般術科測驗] 保留您所有的自動換算與即時紀錄
if mode == "一般術科測驗":
    col1, col2 = st.columns(2)
    with col1:
        test_cat = st.selectbox("🗂️ 類別", ["一般術科", "球類", "田徑", "其他"])
        subject_items = norms_settings_df[norms_settings_df['測驗類別'] != "體適能"]['項目名稱'].unique()
        test_item = st.selectbox("📝 項目", list(subject_items) + ["其他"])
        if test_item == "其他": test_item = st.text_input("✍️ 輸入項目名稱")
    with col2:
        fmt = st.selectbox("📏 格式", ["分數/個數 (純數字)", "秒數 (00.00)"])
        auto_j = st.checkbox("🤖 自動換算分數", value=True)
        manual_m = st.selectbox("🏅 等第", ["優", "甲", "乙", "丙", "丁", "尚未判定"])

    if "秒數" in fmt:
        c1, c2 = st.columns(2)
        final_score = f"{c1.number_input('秒', 0, 99, 13)}.{c2.number_input('毫秒', 0, 99, 0):02d}"
    else: 
        final_score = clean_numeric_string(st.text_input("📊 輸入數值", "0"))

    final_medal = universal_judge("一般術科", test_item, sel_gender, 0, final_score, norms_settings_df) if auto_j else manual_m
    note = st.text_input("💬 備註", "")
    
    # 即時顯示近期紀錄 (補回原本功能)
    st.write("🕒 **近期紀錄：**")
    recent = scores_df[(scores_df['姓名'] == stu['姓名']) & (scores_df['項目'] == test_item)]
    if not recent.empty: st.dataframe(recent[['紀錄時間', '成績', '等第/獎牌']].tail(3), use_container_width=True)

# [B. 114年體適能] 
elif mode == "114年體適能":
    test_cat = "體適能"
    status = st.selectbox("🩺 學生狀態", ["一般生", "身障/重大傷病 (比照銅牌)", "身體羸弱 (比照待加強)"])
    fitness_items = norms_settings_df[norms_settings_df['測驗類別'] == "體適能"]['項目名稱'].unique()
    test_item = st.selectbox("🏃 檢測項目", list(fitness_items))
    if status == "一般生":
        if "跑" in test_item or ":" in str(test_item):
            c1, c2 = st.columns(2)
            final_score, fmt = f"{c1.number_input('分', 0, 20, 8):02d}:{c2.number_input('秒', 0, 59, 0):02d}.0", "秒數 (00:00.0)"
        else:
            val = st.number_input("🔢 數據", 0.0, 500.0, 0.0)
            final_score, fmt = clean_numeric_string(val), "次數/公分"
        final_medal = universal_judge("體適能", test_item, sel_gender, stu['年齡'], final_score, norms_settings_df)
        note = ""
    else:
        final_score, fmt = "N/A", "特殊判定"
        final_medal, note = ("銅牌" if "身障" in status else "待加強"), status

# [C. 🚀 AI 智慧診斷教學] 解決 AI 幻想的核心：直接餵入資料庫文字
elif mode == "🚀 AI 智慧診斷教學":
    st.subheader(f"📹 {stu['姓名']} - 影像分析與技術診斷")
    
    # 找尋該學生已有的成績紀錄供 AI 參考
    available_tests = scores_df[scores_df['姓名'] == stu['姓名']]['項目'].unique().tolist()
    sel_test_ai = st.selectbox("1. 選擇要分析的項目", available_tests if available_tests else ["先記錄成績後再來診斷"])
    
    if sel_test_ai in available_tests:
        # 抓取技術指標與常模 (這一步是防止 AI 幻想的關鍵)
        cri_row = ai_criteria_df[ai_criteria_df["測驗項目"].str.strip() == sel_test_ai.strip()]
        relevant_norms = norms_settings_df[norms_settings_df['項目名稱'] == sel_test_ai].to_string() # 轉為文字直接餵給 AI
        
        if cri_row.empty:
            st.error(f"❌ AI_Criteria 中找不到項目：{sel_test_ai}"); st.stop()
        
        cri = cri_row.iloc[0]
        col_info, col_v = st.columns([1, 1.5])
        with col_info:
            current_raw = scores_df[(scores_df['姓名'] == stu['姓名']) & (scores_df['項目'] == sel_test_ai)].iloc[-1]['成績']
            st.metric("實測數據", f"{current_raw}")
            st.info(f"技術指標：{cri.get('Indicators', '未設定')}")
            with st.expander("📝 查看該項判定常模 (防止 AI 誤判)"):
                st.text(relevant_norms)
        
        with col_v:
            uploaded_v = st.file_uploader("上傳動作影像", type=["mp4", "mov"])
            if uploaded_v: st.video(uploaded_v)

        if st.button("🚀 開始綜合診斷"):
            if not uploaded_v: st.warning("請上傳影片。")
            else:
                with st.spinner("AI 正在比對資料庫常模進行分析..."):
                    try:
                        temp_path = "temp.mp4"
                        with open(temp_path, "wb") as f: f.write(uploaded_v.read())
                        video_file = genai.upload_file(path=temp_path)
                        while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                        
                        # 嚴謹的 Prompt：強制 AI 依照輸入的文字常模說話
                        full_prompt = f"""
                        你是專業體育術科專家。請完全依照以下資料庫數據對【{stu['姓名']}】進行評估：
                        - 登記性別：{sel_gender}
                        - 實測成績：{current_raw}
                        - 資料庫判定標準(常模)：{relevant_norms}
                        - 關鍵技術指標：{cri.get('Indicators', '')}
                        - 教學處方重點：{cri.get('Cues', '')}

                        任務：
                        1. 核對影像性別與登記是否相符。
                        2. 分析影像中動作的優缺點。
                        3. 根據【資料庫判定標準】說明其成績落點。
                        4. 提供具體的【教學處方】。
                        """
                        model = genai.GenerativeModel(MODEL_ID)
                        response = model.generate_content([video_file, full_prompt])
                        st.session_state['ai_report'] = response.text
                        st.session_state['ai_done'] = True
                        st.markdown(response.text)
                        genai.delete_file(video_file.name); os.remove(temp_path)
                    except Exception as e: st.error(f"分析出錯：{e}")

    if st.session_state.get('ai_done'):
        st.divider()
        t_note = st.text_area("老師補充意見")
        if st.button("💾 儲存 AI 診斷結果"):
            new_h = {
                "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "班級": sel_class, "姓名": stu['姓名'], "項目": sel_test_ai,
                "最終得分": "見報告", "AI診斷報告": st.session_state['ai_report'], "老師評語": t_note
            }
            updated_h = pd.concat([ai_history, pd.DataFrame([new_h])], ignore_index=True)
            conn.update(worksheet="Analysis_Results", data=updated_h)
            st.success("✅ 診斷報告已存檔！")

# [D. 數據報表查詢] 完全保留您的編輯與下載功能
elif mode == "📊 數據報表查詢":
    tab1, tab2, tab3 = st.tabs(["👤 個人成績", "👥 班級總覽", "⚙️ 系統管理"])
    with tab1:
        st.dataframe(scores_df[scores_df['姓名'] == stu['姓名']], use_container_width=True)
    with tab2:
        cl_data = scores_df[scores_df['班級'] == sel_class].sort_values(by='座號')
        st.dataframe(cl_data, use_container_width=True)
        st.download_button("📥 下載班級報表", cl_data.to_csv(index=False).encode('utf-8-sig'), f"{sel_class}.csv")
    with tab3:
        st.subheader("📝 常模即時編輯")
        edited = st.data_editor(norms_settings_df, num_rows="dynamic")
        if st.button("💾 同步更新常模"):
            conn.update(worksheet="Norms_Settings", data=edited)
            st.success("常模已更新！"); st.rerun()

# --- 8. 存檔邏輯 (恢復您的「覆蓋/更新」核心機制) ---
if mode in ["一般術科測驗", "114年體適能"]:
    st.divider()
    existing_mask = (scores_df['姓名'] == stu['姓名']) & (scores_df['項目'] == test_item)
    if existing_mask.any():
        st.warning(f"🕒 提醒：已存在 {stu['姓名']} 的 {test_item} 紀錄，存檔將會覆蓋更新。")

    if st.button("💾 確認存檔至雲端試算表"):
        new_row = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "班級": sel_class, "座號": stu['座號'], "姓名": stu['姓名'],
            "測驗類別": test_cat, "項目": test_item, "成績": final_score,
            "顯示格式": fmt, "等第/獎牌": final_medal, "備註": note
        }
        if existing_mask.any():
            # 找到索引並精確覆蓋 (您的原始邏輯)
            for k, v in new_row.items(): scores_df.loc[existing_mask, k] = str(v)
            final_df = scores_df
        else:
            final_df = pd.concat([scores_df, pd.DataFrame([new_row])], ignore_index=True)
        
        conn.update(worksheet="Scores", data=final_df.map(clean_numeric_string))
        st.balloons(); st.success("✅ 成績紀錄已成功存檔！"); st.rerun()

if st.sidebar.button("🚪 登出系統"):
    st.session_state["password_correct"] = False
    st.rerun()
