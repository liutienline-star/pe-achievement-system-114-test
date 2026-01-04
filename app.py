import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import os
import time
import re

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年體育 AI 智慧管理平台", layout="wide", page_icon="🏆")

# API 安全金鑰設定
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "gemini-2.0-flash" 
else:
    st.error("❌ 找不到 API_KEY，請在 Streamlit Secrets 中設定。"); st.stop()

# --- 2. 登入權限管理 ---
def check_password():
    if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True
    st.title("🔒 114學年度術科管理系統 - 登入")
    col1, _ = st.columns([1, 2])
    with col1:
        u = st.text_input("👤 管理員帳號")
        p = st.text_input("🔑 密碼", type="password")
        if st.button("🚀 確認登入"):
            if u == "tienline" and p == "641101":
                st.session_state["password_correct"] = True; st.rerun()
            else: st.error("🚫 帳號或密碼錯誤")
    return False

if not check_password(): st.stop()

# --- 3. 資料讀取與核心邏輯函式 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def clean_numeric_string(val):
    if pd.isna(val) or val == 'nan' or val == "": return ""
    s = str(val).strip()
    return str(int(float(s))) if re.match(r'^\d+\.0$', s) else s

@st.cache_data(ttl=5)
def load_all_data():
    df_c = conn.read(worksheet="AI_Criteria").astype(str)
    df_n = conn.read(worksheet="Norms_Settings").astype(str)
    df_s = conn.read(worksheet="Scores").astype(str)
    df_sl = conn.read(worksheet="Student_List").astype(str)
    try: 
        df_h = conn.read(worksheet="Analysis_Results").astype(str)
    except: 
        df_h = pd.DataFrame(columns=["時間", "班級", "姓名", "項目", "數據分數", "技術分數", "最終修訂分數", "AI診斷報告", "老師評語", "老師修正總分"])
    
    for df in [df_c, df_n, df_s, df_sl, df_h]:
        if not df.empty:
            df.columns = df.columns.astype(str).str.strip()
            for col in df.columns: df[col] = df[col].apply(clean_numeric_string)
    return df_c, df_n, df_s, df_sl, df_h

df_criteria, df_norms, df_scores, df_student_list, df_history = load_all_data()

def parse_time_to_seconds(time_str):
    try:
        s_val = str(time_str).strip()
        if ":" in s_val:
            main = s_val.split('.')[0]
            parts = main.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        return float(s_val)
    except: return 0

def universal_judge(item, gender, age, value, norms_df):
    """回傳 (等第, 數值分數)"""
    try:
        mask = (norms_df['項目名稱'].astype(str) == str(item)) & (norms_df['性別'].astype(str) == str(gender))
        f = norms_df[mask].copy()
        if f.empty: return "無常模", 60
        v = parse_time_to_seconds(value)
        comp = f['比較方式'].iloc[0]
        f['門檻值_num'] = pd.to_numeric(f['門檻值'], errors='coerce')
        f = f.sort_values('門檻值_num', ascending=(comp == "<="))
        for _, row in f.iterrows():
            if (comp == ">=" and v >= row['門檻值_num']) or (comp == "<=" and v <= row['門檻值_num']):
                raw_score = row.get('分數', 60) 
                return row['判定結果'], int(float(raw_score))
        return "待加強", 60
    except: return "判定錯誤", 0

def parse_logic_weights(logic_str):
    """解析權重，預設為 0.7/0.3"""
    try:
        nums = re.findall(r"(\d+)", str(logic_str))
        if len(nums) >= 2:
            w_d, w_t = int(nums[0])/100, int(nums[1])/100
            if (w_d + w_t) == 1.0: return w_d, w_t
    except: pass
    return 0.7, 0.3

# --- 4. 側邊欄 (修正：保證雙向連動版) ---
with st.sidebar:
    st.header("👤 學生與項目選擇")
    
    # 1. 選擇班級
    all_classes = sorted(df_student_list["班級"].unique())
    sel_class = st.selectbox("1. 選擇班級", all_classes, key="class_selector")
    
    # 篩選班級資料並排序座號
    stu_df = df_student_list[df_student_list["班級"] == sel_class].copy()
    stu_df['座號'] = stu_df['座號'].astype(str).str.strip()
    try:
        stu_df['座號_int'] = pd.to_numeric(stu_df['座號'])
        stu_df = stu_df.sort_values('座號_int')
    except:
        stu_df = stu_df.sort_values('座號')

    seat_list = stu_df["座號"].tolist()
    name_list = stu_df["姓名"].tolist()

    # --- 核心同步邏輯 ---
    # 初始化一個全域索引，用來控制兩個選單
    if f"idx_{sel_class}" not in st.session_state:
        st.session_state[f"idx_{sel_class}"] = 0

    # 當「座號」改變時觸發
    def sync_by_seat():
        val = st.session_state.sb_seat
        st.session_state[f"idx_{sel_class}"] = seat_list.index(val)

    # 當「姓名」改變時觸發
    def sync_by_name():
        val = st.session_state.sb_name
        st.session_state[f"idx_{sel_class}"] = name_list.index(val)

    # 顯示兩個連動的選單
    col_seat, col_name = st.columns([1, 2])
    
    with col_seat:
        # 座號選單
        sel_seat = st.selectbox(
            "座號", 
            seat_list, 
            index=st.session_state[f"idx_{sel_class}"],
            key="sb_seat",
            on_change=sync_by_seat
        )

    with col_name:
        # 姓名選單
        sel_name = st.selectbox(
            "2. 選擇學生", 
            name_list, 
            index=st.session_state[f"idx_{sel_class}"],
            key="sb_name",
            on_change=sync_by_name
        )

    # 取得最終選定的學生物件
    curr_stu = stu_df.iloc[st.session_state[f"idx_{sel_class}"]]
    
    # 強制將姓名導出給後續程式使用
    sel_name = curr_stu['姓名']

    st.success(f"📌 {sel_name} ({curr_stu['座號']}號)")
    st.info(f"性別：{curr_stu['性別']} | 年齡：{curr_stu['年齡']}歲")
    
    st.divider()
    if st.button("🚪 登出", use_container_width=True):
        st.session_state["password_correct"] = False
        st.rerun()
# --- 5. 主介面分頁 ---
tab_entry, tab_ai, tab_manage = st.tabs(["📝 成績錄入", "🚀 AI 智慧診斷", "📊 數據報表與管理"])

# [分頁 1：成績錄入 - 體適能格式優化與覆蓋邏輯]
with tab_entry:
    col1, col2 = st.columns(2)
    with col1:
        # 1. 類別連動項目
        test_cat = st.selectbox("🗂️ 類別", ["一般術科", "體適能", "球類", "田徑"], key="entry_cat_v2")
        items = df_norms[df_norms["測驗類別"] == test_cat]["項目名稱"].unique().tolist()
        sel_item = st.selectbox("📝 項目", items + ["其他"], key="entry_item_v2")
        if sel_item == "其他": 
            sel_item = st.text_input("✍️ 輸入項目名稱", key="entry_custom_v2")

    with col2:
        fmt = st.selectbox("📏 格式", ["純數字 (次數/分數)", "秒數 (分:秒)", "秒數 (00.00)"], key="entry_fmt_v2")
        if "分:秒" in fmt:
            c1, c2 = st.columns(2)
            final_val = f"{c1.number_input('分', 0, 20, 8, key='m'):02d}:{c2.number_input('秒', 0, 59, 0, key='s'):02d}.0"
        elif "00.00" in fmt:
            c1, c2 = st.columns(2)
            final_val = f"{c1.number_input('秒', 0, 99, 13, key='ss'):02d}.{c2.number_input('毫秒', 0, 99, 0, key='ms'):02d}"
        else: 
            # 針對「次數」格式，輸入時即確保為整數型態
            val_input = st.number_input("📊 輸入數值", value=0, step=1, key="entry_val_v2")
            final_val = str(int(val_input)) # 強制轉為整數文字，避免產生 .0

    # 2. 呼叫常模判斷 (僅取回獎牌等第)
    res_medal, res_score = universal_judge(sel_item, curr_stu['性別'], curr_stu['年齡'], final_val, df_norms)
    
    # 僅在非「其他」項目且有結果時顯示等第
    if res_medal:
        st.success(f"🎯 常模判定結果：**{res_medal}**")

    # 3. 儲存與覆蓋邏輯 (存入 Scores 表)
    if st.button("💾 儲存/更新成績", use_container_width=True, key="save_score_btn"):
        try:
            new_score = {
                "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "班級": str(sel_class), 
                "姓名": str(sel_name), 
                "項目": str(sel_item),
                "成績": str(final_val), 
                "等第/獎牌": str(res_score), # 後台保留分數供統計，但前端顯示依老師需求過濾
                "備註": str(res_medal)        # 存放：金質、銀質、銅質、中等、待加強
            }
            
            old_scores = conn.read(worksheet="Scores").astype(str)
            
            # 覆蓋邏輯：根據姓名+項目去重，保留最新的一筆
            updated_scores = pd.concat([old_scores, pd.DataFrame([new_score])], ignore_index=True)
            updated_scores = updated_scores.drop_duplicates(subset=["姓名", "項目"], keep="last")
            
            conn.update(worksheet="Scores", data=updated_scores)
            
            st.cache_data.clear() # 清除快取以刷新紀錄
            st.success(f"✅ {sel_name} 的『{sel_item}』成績已成功紀錄！")
            st.rerun()
            
        except Exception as e:
            st.error(f"儲存失敗：{e}")

    # --- 4. 歷史紀錄呈現 (優化格式) ---
    st.divider()
    st.markdown(f"### 🕒 **{sel_name}** - **{sel_item}** 歷史紀錄")

    # 重新讀取確保最新
    df_history = conn.read(worksheet="Scores").astype(str)
    recent = df_history[
        (df_history['姓名'].str.strip() == str(sel_name).strip()) & 
        (df_history['項目'].str.strip() == str(sel_item).strip())
    ].copy()

    if not recent.empty:
        # 數據清理：確保「成績」欄位若為整數，則顯示時不帶 .0
        def format_val(x):
            try:
                if '.' in x and x.split('.')[-1] == '0': # 處理 30.0 這種情況
                    return x.split('.')[0]
                return x
            except: return x

        recent['成績'] = recent['成績'].apply(format_val)
        
        # 僅顯示老師要求的欄位：錄入時間、數值、常模等第
        display_df = recent[['紀錄時間', '成績', '備註']].tail(5)
        display_df.columns = ['錄入時間', '數值', '常模等第']
        
        st.dataframe(display_df, use_container_width=True)
    else:
        st.caption(f"✨ 尚無 {sel_name} 在「{sel_item}」項目的歷史紀錄。")

    import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import os
import time
import re

# --- 1. 初始化與環境設定 ---
st.set_page_config(page_title="114學年度體育智慧管理系統", layout="wide", page_icon="🏆")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "gemini-2.0-flash" 
else:
    st.error("❌ 找不到 API_KEY，請在 Streamlit Secrets 設定。"); st.stop()

# --- 2. 登入管理 ---
if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
if not st.session_state["password_correct"]:
    st.title("🔒 體育成績管理系統 - 登入")
    u = st.text_input("👤 帳號")
    p = st.text_input("🔑 密碼", type="password")
    if st.button("確認登入"):
        if u == "tienline" and p == "641101":
            st.session_state["password_correct"] = True; st.rerun()
        else: st.error("🚫 帳密錯誤")
    st.stop()

# --- 3. 核心功能函式 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def parse_logic_weights(logic_str):
    nums = re.findall(r"(\d+)", str(logic_str))
    if len(nums) >= 2: return int(nums[0])/100, int(nums[1])/100
    return 0.7, 0.3

def clean_numeric(val):
    if pd.isna(val) or val == "": return ""
    s = str(val).strip()
    return str(int(float(s))) if re.match(r'^\d+\.0$', s) else s

@st.cache_data(ttl=0)
def load_data():
    s = conn.read(worksheet="Scores").astype(str).map(clean_numeric)
    sl = conn.read(worksheet="Student_List").astype(str).map(clean_numeric)
    n = conn.read(worksheet="Norms_Settings").astype(str).map(clean_numeric)
    c = conn.read(worksheet="AI_Criteria").astype(str).map(clean_numeric)
    try: a = conn.read(worksheet="Analysis_Results").astype(str)
    except: a = pd.DataFrame(columns=["時間", "班級", "姓名", "項目", "數據分數", "技術分數", "最終修訂分數", "AI診斷報告"])
    return s, sl, n, c, a

df_scores, df_student_list, df_norms, df_criteria, df_analysis = load_data()

# --- 4. 側邊欄：學生選取 ---
with st.sidebar:
    st.header("👤 學生選取")
    all_classes = sorted(df_student_list["班級"].unique())
    sel_class = st.selectbox("選擇班級", all_classes)
    stu_df = df_student_list[df_student_list["班級"] == sel_class].sort_values("座號")
    sel_name = st.selectbox("選擇學生姓名", stu_df["姓名"].tolist())
    curr_stu = stu_df[stu_df["姓名"] == sel_name].iloc[0]
    st.success(f"📌 {sel_name} ({curr_stu['性別']})")

# --- 5. 主分頁介面 ---
tab_entry, tab_ai, tab_report = st.tabs(["📝 成績錄入", "🚀 AI 智慧診斷", "📊 個人/班級報表"])

# [分頁 2：AI 智慧診斷 - 完整不變動邏輯版]
with tab_ai:
    st.header("🚀 AI 動作技術診斷")
    
    # 選擇項目 (僅列出該生已有的成績項目)
    stu_items = df_scores[df_scores["姓名"] == sel_name]["項目"].unique()
    sel_item = st.selectbox("🎯 選擇診斷項目", stu_items if len(stu_items)>0 else ["無紀錄"])

    if len(stu_items) == 0:
        st.warning("⚠️ 此學生尚無錄入成績，請先至『成績錄入』分頁存檔。")
    else:
        # --- 1. 取得學生數據成績 (嚴格保留原始邏輯) ---
        score_row = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_item)]
        last_rec = score_row.iloc[-1]
        raw_val = last_rec.get("等第/獎牌") # 這裡對接 Scores 的數據換算分
        data_score = pd.to_numeric(raw_val, errors='coerce')

        if pd.isna(data_score):
            st.error(f"🛑 錯誤：此項目的數據分數無效，無法計算權重。")
        else:
            # --- 2. 參照 AI_Criteria 規準 ---
            c_rows = df_criteria[df_criteria["測驗項目"] == sel_item]
            if c_rows.empty:
                st.error(f"❌ AI_Criteria 表中找不到項目：{sel_item}"); st.stop()
            
            c_row = c_rows.iloc[0]
            w_data, w_tech = parse_logic_weights(str(c_row.get("評分權重 (Scoring_Logic)", "70,30")))
            indicators = str(c_row.get("具體指標 (Indicators)", ""))
            ai_context = str(c_row.get("AI 指令脈絡 (AI_Context)", "專業體育老師"))
            ai_cues = str(c_row.get("專業指令與建議 (Cues)", ""))

            # --- 3. 介面佈局 ---
            col_i, col_v = st.columns([1, 1.2])
            with col_i:
                st.subheader("📊 診斷參考")
                st.metric("數據得分", f"{data_score} 分")
                st.warning(f"⚖️ 權重：數據 {int(w_data*100)}% / 技術 {int(w_tech*100)}%")
                with st.expander("🔍 檢視具體指標"):
                    st.markdown(f"**【技術規準】**\n{indicators}")
            
            with col_v:
                st.subheader("📹 影片上傳")
                up_v = st.file_uploader(f"上傳【{sel_item}】診斷影片", type=["mp4", "mov"])
                if up_v: st.video(up_v)

            st.divider()

            # --- 4. 執行 AI 診斷 (完整三階段 Prompt) ---
            if st.button(f"🚀 執行 {sel_item} AI 嚴謹診斷", use_container_width=True) and up_v:
                with st.spinner("AI 考官正在比對技術指標..."):
                    try:
                        temp_path = "temp_v.mp4"
                        with open(temp_path, "wb") as f: f.write(up_v.read())
                        video_file = genai.upload_file(path=temp_path)
                        while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                        
                        full_prompt = f"""
                        【身分設定】{ai_context}
                        【受測項目：{sel_item}】
                        
                        ### 第一階段：視覺偵錯 (Compliance Check)
                        1. 比對影片動作是否符合指標："{indicators}"。
                        2. 若項目不符，請立即回報：🛑 項目偵錯錯誤。理由：[具體說明內容]。

                        ### 第二階段：專業技術診斷
                        (僅在第一階段通過時執行)
                        參考建議：{ai_cues}
                        格式：
                        1. [確認動作]：(描述觀察到的特徵)
                        2. [關鍵優化]：(指出技術缺失)
                        3. [訓練處方]：(具體建議)

                        ### 第三階段：技術評分 (Scoring Rubric)
                        嚴格遵守以下指標評分："{indicators}"
                        - 完全達成：90-100分
                        - 達成大部分：80-89分
                        - 基礎達成：75分以上
                        - 未達標：70分以下
                        格式：技術分：XX分。
                        """
                        model = genai.GenerativeModel(MODEL_ID, generation_config={"temperature": 0})
                        response = model.generate_content([video_file, full_prompt])
                        
                        if "🛑" in response.text:
                            st.error(response.text)
                        else:
                            score_match = re.search(r"技術分：(\d+)", response.text)
                            st.session_state['ai_tech_score'] = int(score_match.group(1)) if score_match else 80
                            st.session_state['ai_report'] = response.text
                            st.session_state['ai_done'] = True
                        
                        genai.delete_file(video_file.name)
                        if os.path.exists(temp_path): os.remove(temp_path)
                    except Exception as e: st.error(f"分析失敗：{e}")

            # --- 5. 結果顯示與存檔 ---
            if st.session_state.get('ai_done'):
                st.info(st.session_state['ai_report'])
                tech_input = st.number_input("老師核定技術分", 0, 100, value=st.session_state['ai_tech_score'])
                total_sum = (data_score * w_data) + (tech_input * w_tech)
                st.subheader(f"🏆 最終修訂總分：{total_sum:.1f}")

                if st.button("💾 存入分析報表庫", use_container_width=True):
                    new_entry = {
                        "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "班級": sel_class, "姓名": sel_name, "項目": sel_item,
                        "數據分數": str(data_score), "技術分數": str(tech_input),
                        "最終修訂分數": str(round(total_sum, 2)),
                        "AI診斷報告": st.session_state['ai_report']
                    }
                    updated_df = pd.concat([df_analysis, pd.DataFrame([new_entry])], ignore_index=True).drop_duplicates(subset=["姓名", "項目"], keep="last")
                    conn.update(worksheet="Analysis_Results", data=updated_df)
                    st.success("✅ 紀錄已成功更新！"); st.balloons()

# [分頁 3：數據報表查詢 (加回個人/班級視角)]
with tab_report:
    rep_tab1, rep_tab2 = st.tabs(["👤 個人學習歷程", "👥 班級成績總覽"])
    with rep_tab1:
        st.subheader(f"📊 {sel_name} 的體育表現")
        col_s, col_a = st.columns(2)
        with col_s:
            st.write("**數據成績**")
            st.dataframe(df_scores[df_scores["姓名"]==sel_name][["項目", "成績", "備題", "紀錄時間"]], use_container_width=True)
        with col_a:
            st.write("**AI 技術診斷**")
            st.dataframe(df_analysis[df_analysis["姓名"]==sel_name][["項目", "最終修訂分數", "時間"]], use_container_width=True)
    
    with rep_tab2:
        st.subheader(f"👥 {sel_class} 全班總覽")
        cl_view = df_analysis[df_analysis["班級"] == sel_class]
        st.dataframe(cl_view, use_container_width=True)

# [分頁 3：數據管理]
with tab_manage:
    m_tab1, m_tab2, m_tab3 = st.tabs(["📋 班級成績單", "⚙️ 常模管理", "🔄 系統重算"])
    with m_tab1:
        st.dataframe(df_scores[df_scores["班級"] == sel_class], use_container_width=True)
    with m_tab2:
        edited_n = st.data_editor(df_norms, num_rows="dynamic")
        if st.button("💾 更新常模"): conn.update(worksheet="Norms_Settings", data=edited_n); st.rerun()
    with m_tab3:
        if st.button("🚀 一鍵重算全校等第"):
            st.success("功能開發中，目前請透過更新常模後手動錄入更新。")
