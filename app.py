import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import os
import time
import re

# --- 1. 系統初始與安全性設定 ---
st.set_page_config(page_title="114學年度體育智慧管理平台", layout="wide", page_icon="🏆")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "gemini-2.0-flash" 
else:
    st.error("❌ 找不到 API_KEY，請在 Streamlit Secrets 設定。"); st.stop()

# --- 2. 登入權限管理 ---
if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
if not st.session_state["password_correct"]:
    st.title("🔒 體育成績管理系統 - 登入")
    col1, _ = st.columns([1, 2])
    with col1:
        u = st.text_input("👤 帳號")
        p = st.text_input("🔑 密碼", type="password")
        if st.button("🚀 確認登入", use_container_width=True):
            if u == "tienline" and p == "641101":
                st.session_state["password_correct"] = True; st.rerun()
            else: st.error("🚫 帳號或密碼錯誤")
    st.stop()

# --- 3. 核心資料工具函式 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def clean_numeric_string(val):
    if pd.isna(val) or val == 'nan' or val == "": return ""
    s = str(val).strip()
    return str(int(float(s))) if re.match(r'^\d+\.0$', s) else s

def parse_time_to_seconds(time_str):
    try:
        s_val = str(time_str).strip()
        if ":" in s_val:
            parts = s_val.split('.')[0].split(':')
            return int(parts[0]) * 60 + int(parts[1])
        return float(s_val)
    except: return 0

def parse_logic_weights(logic_str):
    # 支援「數據(70%), 技術(30%)」或「70, 30」格式
    nums = re.findall(r"(\d+)", str(logic_str))
    if len(nums) >= 2: return int(nums[0])/100, int(nums[1])/100
    return 0.7, 0.3

@st.cache_data(ttl=0)
def load_all_sheets():
    s = conn.read(worksheet="Scores").astype(str).map(clean_numeric_string)
    sl = conn.read(worksheet="Student_List").astype(str).map(clean_numeric_string)
    n = conn.read(worksheet="Norms_Settings").astype(str).map(clean_numeric_string)
    c = conn.read(worksheet="AI_Criteria").astype(str).map(clean_numeric_string)
    try: a = conn.read(worksheet="Analysis_Results").astype(str).map(clean_numeric_string)
    except: a = pd.DataFrame(columns=["時間", "班級", "姓名", "項目", "數據分數", "技術分數", "最終修訂分數", "AI診斷報告"])
    return s, sl, n, c, a

df_scores, df_student_list, df_norms, df_criteria, df_analysis = load_all_sheets()

# --- 4. 側邊欄：單一整合學生選單 ---
with st.sidebar:
    st.header("👤 學生與導覽")
    all_classes = sorted(df_student_list["班級"].unique())
    sel_class = st.selectbox("1. 選擇班級", all_classes)
    
    # 取得該班學生並按座號排序
    stu_df = df_student_list[df_student_list["班級"] == sel_class].copy()
    stu_df["座號_int"] = pd.to_numeric(stu_df["座號"], errors="coerce")
    stu_df = stu_df.sort_values("座號_int")
    
    # 整合顯示名稱："[01] 王小明"
    stu_options = [f"[{row['座號']}] {row['姓名']}" for _, row in stu_df.iterrows()]
    sel_option = st.selectbox("2. 選擇學生", stu_options)
    
    # 核心變數解析
    sel_name = re.search(r"\] (.*)", sel_option).group(1)
    curr_stu = stu_df[stu_df["姓名"] == sel_name].iloc[0]
    
    st.divider()
    st.success(f"📌 {sel_name}\n\n性別：{curr_stu['性別']} | 年齡：{curr_stu['年齡']}")
    if st.button("🚪 登出系統"): st.session_state["password_correct"] = False; st.rerun()

# --- 5. 判定引擎：術科與體適能 ---
def universal_judge(category, item, gender, age, value, norms_df):
    try:
        mask = (norms_df['測驗類別'] == category) & (norms_df['項目名稱'] == item) & (norms_df['性別'] == gender)
        f = norms_df[mask].copy()
        if f.empty: return "無常模", 60
        age_int = int(float(age)) if age else 0
        f = f[(f['年齡'].astype(float).astype(int) == age_int) | (f['年齡'].astype(float).astype(int) == 0)]
        if f.empty: return "待加強", 60
        v = parse_time_to_seconds(value)
        comp = f['比較方式'].iloc[0]
        f['門檻值_num'] = pd.to_numeric(f['門檻值'], errors='coerce')
        sorted_norms = f.sort_values(by='門檻值_num', ascending=(comp == "<="))
        for _, rule in sorted_norms.iterrows():
            if (comp == ">=" and v >= rule['門檻值_num']) or (comp == "<=" and v <= rule['門檻值_num']):
                return rule['判定結果'], int(float(rule.get('分數', 60)))
    except: pass
    return "待加強", 60

# --- 6. 主頁面：功能分頁 ---
st.title("🏆 114學年度體育智慧管理平台")
tab_entry, tab_ai, tab_report, tab_manage = st.tabs(["📝 成績錄入", "🚀 AI 智慧診斷", "📊 數據報表", "⚙️ 後台管理"])

# [分頁 1：成績錄入]
with tab_entry:
    st.subheader(f"📝 {sel_name} 成績資料錄入")
    c1, c2 = st.columns(2)
    with c1:
        t_cat = st.selectbox("🗂️ 測驗類別", ["體適能", "一般術科", "球類", "田徑"])
        items = df_norms[df_norms["測驗類別"] == t_cat]["項目名稱"].unique().tolist()
        t_item = st.selectbox("🎯 項目名稱", items)
    with c2:
        f_val = st.text_input("📊 輸入成績 (體適能輸整數 / 秒數輸 分:秒)", "0")
        res_medal, res_score = universal_judge(t_cat, t_item, curr_stu['性別'], curr_stu['年齡'], f_val, df_norms)
        st.info(f"系統判定：**{res_medal}** (數據得分：{res_score})")

    if st.button("💾 儲存並覆蓋現有成績", use_container_width=True):
        new_row = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M"), "班級": sel_class, "座號": curr_stu['座號'],
            "姓名": sel_name, "項目": t_item, "成績": f_val, "等第/獎牌": str(res_score), "備註": res_medal, "測驗類別": t_cat
        }
        df_scores = pd.concat([df_scores, pd.DataFrame([new_row])], ignore_index=True).drop_duplicates(subset=["姓名", "項目"], keep="last")
        conn.update(worksheet="Scores", data=df_scores)
        st.cache_data.clear(); st.success("✅ 成績已錄入資料庫！")

# [分頁 2：AI 智慧診斷 - 整合檔案二完整邏輯]
with tab_ai:
    st.header("🚀 AI 專業技術影像診斷")
    stu_items = df_scores[df_scores["姓名"] == sel_name]["項目"].unique()
    
    if len(stu_items) == 0:
        st.warning("⚠️ 該生尚無成績錄入，無法診斷。")
    else:
        sel_item = st.selectbox("🎯 選擇要診斷的項目", stu_items)
        
        # --- 檔案二邏輯：取得數據成績 ---
        score_row = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_item)]
        last_rec = score_row.iloc[-1]
        data_score = pd.to_numeric(last_rec.get("等第/獎牌"), errors='coerce')
        
        if pd.isna(data_score):
            st.error("🛑 錯誤：此項目無有效數據分數。"); st.stop()
            
        # --- 檔案二邏輯：參照 AI_Criteria ---
        c_row = df_criteria[df_criteria["測驗項目"] == sel_item]
        if c_row.empty: st.error(f"❌ 規準表找不到項目：{sel_item}"); st.stop()
        c_row = c_row.iloc[0]
        
        w_data, w_tech = parse_logic_weights(c_row.get("評分權重 (Scoring_Logic)"))
        indicators = str(c_row.get("具體指標 (Indicators)", ""))
        ai_context = str(c_row.get("AI 指令脈絡 (AI_Context)", "專業體育老師"))
        ai_cues = str(c_row.get("專業指令與建議 (Cues)", ""))

        col_i, col_v = st.columns([1, 1.2])
        with col_i:
            st.subheader("📊 診斷參考")
            st.metric("數據得分", f"{data_score} 分")
            st.warning(f"⚖️ 權重：數據 {int(w_data*100)}% / 技術 {int(w_tech*100)}%")
            with st.expander("🔍 檢視技術指標規準"): st.markdown(indicators)
            
        with col_v:
            st.subheader("📹 影片上傳")
            up_v = st.file_uploader(f"請上傳【{sel_item}】影片", type=["mp4", "mov"])
            if up_v: st.video(up_v)

        if st.button("🚀 開始嚴謹分析", use_container_width=True) and up_v:
            with st.spinner("AI 考官正在以最高規準進行技術對照..."):
                try:
                    temp_path = "temp_analysis.mp4"
                    with open(temp_path, "wb") as f: f.write(up_v.read())
                    v_file = genai.upload_file(path=temp_path)
                    while v_file.state.name == "PROCESSING": time.sleep(2); v_file = genai.get_file(v_file.name)
                    
                    # 檔案二核心 Prompt 完整植入
                    full_prompt = f"""
                    【身分設定：最高級別考官】脈絡：{ai_context}
                    【受測項目：{sel_item}】
                    
                    ### 第一階段：視覺偵錯 (🛑)
                    1. 比對影片動作是否符合指標："{indicators}"。
                    2. 若項目不符，立即回報：🛑 項目偵錯錯誤。理由：[具體說明內容]。

                    ### 第二階段：專業技術診斷報告 (參考建議：{ai_cues})
                    格式：1.[確認動作] 2.[關鍵優化] 3.[訓練處方]

                    ### 第三階段：技術評分 (嚴格遵守指標："{indicators}")
                    - 完全達成：90-100 | 部分達成：80-89 | 基礎達成：75+ | 未達標：70以下
                    格式：技術分：XX分。
                    """
                    model = genai.GenerativeModel(MODEL_ID, generation_config={"temperature": 0})
                    resp = model.generate_content([v_file, full_prompt])
                    
                    if "🛑" in resp.text:
                        st.error(resp.text)
                    else:
                        st.session_state['ai_report'] = resp.text
                        st.session_state['ai_tech_score'] = int(re.search(r"技術分：(\d+)", resp.text).group(1)) if re.search(r"技術分：(\d+)", resp.text) else 80
                        st.session_state['ai_done'] = True
                    
                    genai.delete_file(v_file.name)
                    if os.path.exists(temp_path): os.remove(temp_path)
                except Exception as e: st.error(f"分析失敗：{e}")

        if st.session_state.get('ai_done'):
            st.info(st.session_state['ai_report'])
            t_input = st.number_input("核定技術評分", 0, 100, value=st.session_state['ai_tech_score'])
            total = (data_score * w_data) + (t_input * w_tech)
            st.subheader(f"🏆 最終建議總分：{total:.1f}")
            if st.button("💾 確認並存入 Analysis_Results"):
                new_a = {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"), "班級": sel_class, "姓名": sel_name, "項目": sel_item,
                    "數據分數": str(data_score), "技術分數": str(t_input), "最終修訂分數": str(round(total, 2)), "AI診斷報告": st.session_state['ai_report']
                }
                df_analysis = pd.concat([df_analysis, pd.DataFrame([new_a])], ignore_index=True).drop_duplicates(subset=["姓名", "項目"], keep="last")
                conn.update(worksheet="Analysis_Results", data=df_analysis)
                st.success("✅ 診斷紀錄已更新！")

# [分頁 3：數據報表 - 完整整合個人/班級]
with tab_report:
    r1, r2 = st.tabs(["👤 個人學習歷程單", "👥 班級成績總覽"])
    with r1:
        st.subheader(f"📊 {sel_name} 成績報表")
        ca, cb = st.columns(2)
        with ca:
            st.write("**📝 原始數據紀錄**")
            p_s = df_scores[df_scores["姓名"] == sel_name]
            st.dataframe(p_s[["項目", "成績", "備註", "紀錄時間"]], use_container_width=True)
        with cb:
            st.write("**🚀 AI 診斷分析**")
            p_a = df_analysis[df_analysis["姓名"] == sel_name]
            st.dataframe(p_a[["項目", "最終修訂分數", "時間"]], use_container_width=True)
    with r2:
        st.subheader(f"👥 {sel_class} 班級成績全覽")
        st.dataframe(df_scores[df_scores["班級"] == sel_class], use_container_width=True)
        st.download_button("📥 下載完整 CSV 報表", df_scores[df_scores["班級"] == sel_class].to_csv(index=False).encode('utf-8-sig'), f"{sel_class}_report.csv")

# [分頁 4：後台管理]
with tab_manage:
    st.subheader("🛠️ 系統資料即時維護")
    with st.expander("1. 編輯測驗常模 (Norms_Settings)"):
        en = st.data_editor(df_norms, num_rows="dynamic")
        if st.button("💾 更新常模數據"): conn.update(worksheet="Norms_Settings", data=en); st.success("常模已同步！")
    with st.expander("2. 編輯 AI 指標規準 (AI_Criteria)"):
        ec = st.data_editor(df_criteria, num_rows="dynamic")
        if st.button("💾 更新 AI 指標"): conn.update(worksheet="AI_Criteria", data=ec); st.success("指標已同步！")
