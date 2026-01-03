import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import re
import os
import time

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年度體育成績管理系統", layout="wide")

# --- 2. 登入權限管理 (完全保留您的帳密邏輯) ---
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

# --- 4. 資料庫連線與讀取 (包含 AI 模式所需的分頁) ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
def load_full_data():
    try:
        # 讀取所有必要分頁
        df_s = conn.read(worksheet="Scores", ttl="0s").astype(str)
        df_sl = conn.read(worksheet="Student_List", ttl="0s").astype(str)
        df_n = conn.read(worksheet="Norms_Settings", ttl="0s").astype(str)
        df_c = conn.read(worksheet="AI_Criteria", ttl="0s").astype(str)
        try:
            df_h = conn.read(worksheet="Analysis_Results", ttl="0s").astype(str)
        except:
            df_h = pd.DataFrame()
        
        # 清理所有欄位名稱空格
        for df in [df_s, df_sl, df_n, df_c, df_h]:
            if not df.empty:
                df.columns = df.columns.astype(str).str.strip()
        return df_s, df_sl, df_n, df_c, df_h
    except Exception as e:
        st.error(f"資料讀取失敗，請確認雲端表名：{e}"); st.stop()

scores_df, student_list, norms_df, criteria_df, analysis_history = load_full_data()

# --- 5. 核心判定輔助函式 (完全保留您的運算邏輯) ---
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

# --- 6. 側邊欄：學生選取 (保留原功能並加強性別抓取) ---
scores_df = scores_df.map(clean_numeric_string)
student_list = student_list.map(clean_numeric_string)

with st.sidebar:
    st.header("🏆 系統控制面板")
    if not student_list.empty:
        cl_list = sorted(student_list['班級'].unique())
        sel_class = st.selectbox("🏫 選擇班級", cl_list)
        stu_df = student_list[student_list['班級'] == sel_class]
        no_list = stu_df['座號'].sort_values(key=lambda x: pd.to_numeric(x, errors='coerce')).unique()
        sel_no = st.selectbox("🔢 選擇座號", no_list)
        stu = stu_df[stu_df['座號'] == sel_no].iloc[0]
        
        # 確保性別欄位被正確讀取
        g_col = next((c for c in student_list.columns if "性" in c), "性別")
        sel_gender = str(stu[g_col]).strip()
        st.info(f"📌 {stu['姓名']} | {sel_gender} | {stu['年齡']}歲")
    else: st.stop()

# --- 7. 主介面：分頁模式 (按順序排列) ---
mode = st.radio("🎯 功能切換", ["一般術科測驗", "114年體適能", "🚀 AI 智慧技術診斷", "📊 數據報表查詢"], horizontal=True)

# [模式 A：一般術科測驗] 完全保留您的原版邏輯
if mode == "一般術科測驗":
    col1, col2 = st.columns(2)
    with col1:
        test_cat = st.selectbox("🗂️ 類別", ["一般術科", "球類", "田徑", "其他"])
        subject_items = norms_df[norms_df['測驗類別'] != "體適能"]['項目名稱'].unique()
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

    final_medal = universal_judge("一般術科", test_item, sel_gender, 0, final_score, norms_df) if auto_j else manual_m
    note = st.text_input("💬 備註", "")

# [模式 B：114年體適能] 完全保留您的判定邏輯
elif mode == "114年體適能":
    test_cat = "體適能"
    status = st.selectbox("🩺 學生狀態", ["一般生", "身障/重大傷病 (比照銅牌)", "身體羸弱 (比照待加強)"])
    fitness_items = norms_df[norms_df['測驗類別'] == "體適能"]['項目名稱'].unique()
    test_item = st.selectbox("🏃 檢測項目", list(fitness_items))
    if status == "一般生":
        if "跑" in test_item or ":" in str(test_item):
            c1, c2 = st.columns(2)
            final_score, fmt = f"{c1.number_input('分', 0, 20, 8):02d}:{c2.number_input('秒', 0, 59, 0):02d}.0", "秒數 (00:00.0)"
        else:
            val = st.number_input("🔢 數據", 0.0, 500.0, 0.0)
            final_score, fmt = clean_numeric_string(val), "次數/公分"
        final_medal = universal_judge("體適能", test_item, sel_gender, stu['年齡'], final_score, norms_df)
        note = ""
    else:
        final_score, fmt = "N/A", "特殊判定"
        final_medal, note = ("銅牌" if "身障" in status else "待加強"), status

# [模式 C：🚀 AI 智慧技術診斷] 這是修正幻想分數的核心
elif mode == "🚀 AI 智慧技術診斷":
    st.subheader(f"📹 {stu['姓名']} - 影像分析偵測")
    stu_recs = scores_df[scores_df['姓名'] == stu['姓名']]
    sel_test_ai = st.selectbox("1. 選擇要診斷的項目", stu_recs['項目'].unique().tolist())
    
    if sel_test_ai:
        # 抓取該生該項目的最近一次成績
        raw_score = stu_recs[stu_recs['項目'] == sel_test_ai].iloc[-1]['成績']
        match_cri = criteria_df[criteria_df["測驗項目"].str.strip() == sel_test_ai.strip()]
        
        if match_cri.empty:
            st.error(f"❌ 在 AI_Criteria 中找不到項目：{sel_test_ai}")
        else:
            cri = match_cri.iloc[0]
            col_l, col_r = st.columns([1, 1.5])
            with col_l:
                st.metric("實測數據", raw_score)
                # 抓取該項目專屬常模文字
                item_norms_text = norms_df[norms_df['項目名稱'] == sel_test_ai].to_string(index=False)
                with st.expander("📉 本項評分參考依據"):
                    st.text(item_norms_text)
            with col_r:
                uploaded_v = st.file_uploader("上傳動作影片", type=["mp4", "mov"])
                if uploaded_v: st.video(uploaded_v)

            if st.button("🚀 啟動 AI 影像深度分析"):
                if not uploaded_v: st.warning("請先上傳影片。")
                else:
                    with st.spinner("AI 正在比對您的設定進行評估..."):
                        try:
                            temp_path = "temp_ai.mp4"
                            with open(temp_path, "wb") as f: f.write(uploaded_v.read())
                            video_file = genai.upload_file(path=temp_path)
                            while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                            
                            # 強制 AI 讀取您的試算表文字，嚴禁幻想
                            full_prompt = f"""
                            你是一位嚴謹的術科專家。請完全依照以下【資料庫規則】對影片進行評分。
                            【學生資料】姓名：{stu['姓名']}, 性別：{sel_gender}, 成績：{raw_score}
                            【評分規則 - 數據部分】(在此範圍內的數據才給分)：
                            {item_norms_text}
                            【評分規則 - 技術指標】：{cri.get('Indicators', '')}
                            【計算權重與邏輯】：{cri.get('Logic', '')}
                            【指導建議關鍵字】：{cri.get('Cues', '')}
                            
                            請輸出：1.性別檢核 2.動作缺點分析 3.根據邏輯得出的總分 4.改進建議。
                            """
                            model = genai.GenerativeModel(MODEL_ID)
                            response = model.generate_content([video_file, full_prompt])
                            st.session_state['ai_res'] = response.text
                            st.session_state['ai_done'] = True
                            genai.delete_file(video_file.name); os.remove(temp_path)
                        except Exception as e: st.error(f"AI 分析失敗：{e}")

            if st.session_state.get('ai_done'):
                st.markdown(st.session_state['ai_res'])
                t_note = st.text_area("老師補充評語")
                t_score = st.text_input("最終判定得分 (可修改)")
                if st.button("💾 確認存檔至雲端"):
                    # 存入 Analysis_Results
                    new_res = {
                        "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "班級": sel_class, "姓名": stu['姓名'], "項目": sel_test_ai,
                        "最終得分": t_score, "AI診斷報告": st.session_state['ai_res'], "老師評語": t_note
                    }
                    conn.update(worksheet="Analysis_Results", data=pd.concat([analysis_history, pd.DataFrame([new_res])], ignore_index=True))
                    st.success("✅ 診斷結果已儲存！")

# [模式 D：數據報表查詢] 
elif mode == "📊 數據報表查詢":
    tab1, tab2 = st.tabs(["👤 個人成績單", "👥 班級總覽"])
    with tab1:
        st.dataframe(scores_df[scores_df['姓名'] == stu['姓名']], use_container_width=True)
    with tab2:
        st.dataframe(scores_df[scores_df['班級'] == sel_class].sort_values(by='座號'), use_container_width=True)

# --- 8. 存檔邏輯 (保留您最核心的「覆蓋修正」功能) ---
if mode in ["一般術科測驗", "114年體適能"]:
    st.divider()
    existing_mask = (scores_df['姓名'] == stu['姓名']) & (scores_df['項目'] == test_item)
    if st.button("💾 儲存測驗成績"):
        new_row = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "班級": sel_class, "座號": stu['座號'], "姓名": stu['姓名'],
            "測驗類別": test_cat, "項目": test_item, "成績": final_score,
            "顯示格式": fmt, "等第/獎牌": final_medal, "備註": note
        }
        if existing_mask.any():
            for k, v in new_row.items(): scores_df.loc[existing_mask, k] = str(v)
            final_df = scores_df
        else:
            final_df = pd.concat([scores_df, pd.DataFrame([new_row])], ignore_index=True)
        
        conn.update(worksheet="Scores", data=final_df.map(clean_numeric_string))
        st.balloons(); st.success("✅ 成績已成功同步至 Google Sheets！"); st.rerun()

if st.sidebar.button("🚪 登出系統"):
    st.session_state["password_correct"] = False
    st.rerun()
