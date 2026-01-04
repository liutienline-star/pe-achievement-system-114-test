import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import os
import time
import re

# --- 1. 頁面與權限設定 ---
st.set_page_config(page_title="114學年術科 AI 智慧管理平台", layout="wide", page_icon="🏆")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True
    st.title("🔒 系統登入")
    u = st.text_input("👤 管理員帳號")
    p = st.text_input("🔑 密碼", type="password")
    if st.button("🚀 確認登入"):
        if u == "tienline" and p == "641101":
            st.session_state["password_correct"] = True
            st.rerun()
        else: st.error("🚫 帳號或密碼錯誤")
    return False

if not check_password(): st.stop()

# AI 初始化
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "models/gemini-2.5-flash"
else:
    st.error("❌ 找不到 API_KEY"); st.stop()

# --- 2. 核心資料引擎 (保留老師所有的清理與緩存設定) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def clean_numeric_string(val):
    if pd.isna(val) or val == 'nan' or val == "": return ""
    s = str(val).strip()
    return str(int(float(s))) if re.match(r'^\d+\.0$', s) else s

@st.cache_data(ttl=5) # 老師要求的 5 秒同步
def load_data():
    try:
        df_c = conn.read(worksheet="AI_Criteria")
        df_n = conn.read(worksheet="Norms_Settings")
        df_s = conn.read(worksheet="Scores")
        df_sl = conn.read(worksheet="Student_List")
        try: df_h = conn.read(worksheet="Analysis_Results")
        except: df_h = pd.DataFrame()
        
        # 欄位清理
        for df in [df_c, df_n, df_s, df_sl, df_h]:
            if not df.empty: df.columns = df.columns.astype(str).str.strip()
        
        # 數值資料清理 (解決 .0 問題)
        df_s = df_s.map(clean_numeric_string)
        df_sl = df_sl.map(clean_numeric_string)
        
        return df_c, df_n, df_s, df_sl, df_h
    except Exception as e:
        st.error(f"資料讀取失敗：{e}"); st.stop()

df_criteria, df_norms, df_scores, df_student_list, df_history = load_data()

# --- 3. 判定引擎 (保留老師的邏輯) ---
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
        ascending = False if comp == ">=" else True
        sorted_norms = filtered.sort_values(by='門檻值', key=lambda x: x.astype(float), ascending=ascending)
        for _, rule in sorted_norms.iterrows():
            if (comp == ">=" and v >= float(rule['門檻值'])) or (comp == "<=" and v <= float(rule['門檻值'])):
                return rule['判定結果']
    except: pass
    return "待加強"

# --- 4. 側邊欄：統一過濾器 (解決所有功能的人員選擇一致性) ---
with st.sidebar:
    st.header("👤 人員選擇")
    cl_list = sorted(df_student_list['班級'].unique().tolist())
    sel_class = st.selectbox("🏫 選擇班級", cl_list)
    
    stu_df = df_student_list[df_student_list['班級'] == sel_class]
    no_list = sorted(stu_df['座號'].unique().tolist(), key=lambda x: int(x))
    sel_no = st.selectbox("🔢 選擇座號", no_list)
    
    stu = stu_df[stu_df['座號'] == sel_no].iloc[0]
    sel_name = stu['姓名']
    # 跨表抓性別邏輯
    g_col = next((c for c in df_student_list.columns if "性" in c), "性別")
    sel_gender = str(stu[g_col]).strip()
    sel_age = stu.get('年齡', '0')
    
    st.success(f"📌 {sel_name} | {sel_gender} | {sel_age}歲")
    if st.button("🚪 登出"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- 5. 主分頁導覽 ---
st.title("🏆 114學年體育智慧教學管理系統")
tab_record, tab_ai, tab_admin = st.tabs(["📝 成績登錄與對照", "🚀 AI 智慧診斷教學", "📊 班級報表與管理"])

# [分頁 1：成績登錄] - 完整保留老師原本的對照功能
with tab_record:
    mode_rec = st.radio("類別", ["114年體適能", "一般術科測驗"], horizontal=True)
    
    col1, col2 = st.columns(2)
    with col1:
        cat_filter = "體適能" if mode_rec == "114年體適能" else "一般術科"
        items = df_norms[df_norms['測驗類別'].str.contains(cat_filter)]['項目名稱'].unique()
        sel_item = st.selectbox("📝 測驗項目", list(items))
        
    with col2:
        if "跑" in sel_item or ":" in sel_item:
            c1, c2 = st.columns(2)
            score_input = f"{c1.number_input('分', 0, 20, 8):02d}:{c2.number_input('秒', 0, 59, 0):02d}.0"
        else:
            score_input = st.text_input("📊 輸入數值", "0")

    # 即時判定
    final_judge = universal_judge(cat_filter, sel_item, sel_gender, sel_age, score_input, df_norms)
    st.write(f"📢 判定結果：**{final_judge}**")
    
    # 🕒 老師最重視的：歷史紀錄即時方塊
    st.subheader("🕒 該生近期測驗紀錄")
    recent = df_scores[(df_scores['姓名'] == sel_name) & (df_scores['項目'] == sel_item)]
    if not recent.empty:
        st.dataframe(recent[['紀錄時間', '成績', '等第/獎牌']].tail(3), use_container_width=True)
    else: st.info("此學生目前尚無歷史紀錄。")

    if st.button("💾 儲存成績"):
        new_row = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "班級": sel_class, "座號": sel_no, "姓名": sel_name,
            "測驗類別": cat_filter, "項目": sel_item, "成績": score_input,
            "等第/獎牌": final_judge
        }
        # 覆蓋或新增邏輯
        mask = (df_scores['姓名'] == sel_name) & (df_scores['項目'] == sel_item)
        if mask.any():
            for k, v in new_row.items(): df_scores.loc[mask, k] = v
            updated_df = df_scores
        else:
            updated_df = pd.concat([df_scores, pd.DataFrame([new_row])], ignore_index=True)
        
        conn.update(worksheet="Scores", data=updated_df)
        st.success("✅ 成績已同步至雲端！"); st.rerun()

# [分頁 2：AI 智慧診斷] - 完整保留老師的分析提示與回寫邏輯
with tab_ai:
    # 讓老師選擇要分析的項目 (從該生的實測紀錄中選)
    available_tests = df_scores[df_scores["姓名"] == sel_name]["項目"].unique().tolist()
    if not available_tests:
        st.warning("請先在「成績登錄」分頁為該學生建立至少一項成績紀錄。")
    else:
        sel_test_ai = st.selectbox("選擇診斷項目", available_tests)
        raw_score = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_test_ai)].iloc[-1]["成績"]

        # 抓取 AI 準則
        match_rows = df_criteria[df_criteria["測驗項目"].str.strip() == sel_test_ai.strip()]
        if match_rows.empty:
            st.error(f"AI_Criteria 中找不到項目：{sel_test_ai}"); st.stop()
        
        c_row = match_rows.iloc[0]
        indicators = c_row.get("Indicators", "")
        cues = c_row.get("Cues", "")
        logic = c_row.get("Logic", "")
        unit = c_row.get("Unit", "")

        col_info, col_video = st.columns([1, 1.5])
        with col_info:
            st.subheader("📊 診斷參考")
            st.metric(label=f"實測成績 ({unit})", value=raw_score)
            st.markdown(f"**技術指標：**\n{indicators}")
            with st.expander("⏳ 診斷歷史"):
                past_h = df_history[(df_history["姓名"] == sel_name) & (df_history["項目"] == sel_test_ai)]
                st.dataframe(past_h[["時間", "最終得分"]].tail(3), hide_index=True)

        with col_video:
            st.subheader("📹 影片上傳與分析")
            uploaded_v = st.file_uploader("上傳動作影片", type=["mp4", "mov"])
            if uploaded_v: st.video(uploaded_v)
            
            if st.button("🚀 開始 AI 分析"):
                if not uploaded_v: st.warning("請上傳影片。")
                else:
                    with st.spinner("AI 分析中..."):
                        temp_path = "temp.mp4"
                        with open(temp_path, "wb") as f: f.write(uploaded_v.read())
                        video_file = genai.upload_file(path=temp_path)
                        while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                        
                        prompt = f"""
                        你是一位專業體育評分專家。
                        【基本資料】姓名：{sel_name}, 性別：{sel_gender}, 項目：{sel_test_ai}, 成績：{raw_score}
                        【任務】
                        1. 視覺核對：影片人物若非{sel_gender}性請警示。
                        2. 專業分析：參考指標 {indicators}。
                        3. 給予建議：參考處方 {cues}。
                        """
                        model = genai.GenerativeModel(MODEL_ID)
                        response = model.generate_content([video_file, prompt])
                        st.session_state['report'] = response.text
                        st.session_state['done'] = True
                        st.markdown(response.text)
                        genai.delete_file(video_file.name); os.remove(temp_path)

        if st.session_state.get('done'):
            t_note = st.text_area("老師補充評語")
            if st.button("💾 存入 Analysis_Results"):
                new_h = {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "班級": sel_class, "姓名": sel_name, "項目": sel_test_ai,
                    "最終得分": raw_score, "AI診斷報告": st.session_state['report'], "老師評語": t_note
                }
                updated_h = pd.concat([df_history, pd.DataFrame([new_h])], ignore_index=True)
                conn.update(worksheet="Analysis_Results", data=updated_h)
                st.success("診斷紀錄已存檔！"); st.cache_data.clear()

# [分頁 3：管理報表] - 保留老師的 Data Editor 與重算工具
with tab_admin:
    st.subheader(f"👥 {sel_class} 班級成績總覽")
    cl_data = df_scores[df_scores['班級'] == sel_class]
    st.dataframe(cl_data, use_container_width=True)
    
    st.divider()
    st.subheader("🛠️ 常模管理")
    new_norms = st.data_editor(df_norms, num_rows="dynamic")
    if st.button("💾 同步更新常模"):
        conn.update(worksheet="Norms_Settings", data=new_norms)
        st.success("常模已更新！")
