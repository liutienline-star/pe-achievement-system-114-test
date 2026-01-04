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

# --- 4. 側邊欄 (增加座號同步選擇功能) ---
with st.sidebar:
    st.header("👤 學生與項目選擇")
    
    # 1. 選擇班級
    all_classes = sorted(df_student_list["班級"].unique())
    sel_class = st.selectbox("1. 選擇班級", all_classes)
    
    # 篩選該班級學生
    stu_df = df_student_list[df_student_list["班級"] == sel_class].copy()
    
    # 確保座號是數字排序 (先轉型為 int 再排序，避免出現 1, 10, 2 這種排序)
    try:
        stu_df['座號_int'] = stu_df['座號'].astype(int)
        stu_df = stu_df.sort_values('座號_int')
    except:
        stu_df = stu_df.sort_values('座號')

    # 準備選項清單
    seat_list = stu_df["座號"].tolist()
    name_list = stu_df["姓名"].tolist()

    # 建立連動邏輯
    col_seat, col_name = st.columns([1, 2])
    
    with col_seat:
        # 如果 session_state 還沒有紀錄，預設選第一個
        if f"seat_idx_{sel_class}" not in st.session_state:
            st.session_state[f"seat_idx_{sel_class}"] = 0
            
        sel_seat = st.selectbox(
            "座號", 
            seat_list, 
            index=st.session_state[f"seat_idx_{sel_class}"],
            key=f"sb_seat_{sel_class}"
        )
        # 更新當前索引
        current_idx = seat_list.index(sel_seat)
        st.session_state[f"seat_idx_{sel_class}"] = current_idx

    with col_name:
        sel_name = st.selectbox(
            "2. 選擇學生姓名", 
            name_list, 
            index=st.session_state[f"seat_idx_{sel_class}"],
            key=f"sb_name_{sel_class}"
        )
        # 再次確保索引同步（如果使用者改選姓名，也會同步座號）
        current_idx = name_list.index(sel_name)
        st.session_state[f"seat_idx_{sel_class}"] = current_idx

    # 取得最終選定的學生資料
    curr_stu = stu_df.iloc[st.session_state[f"seat_idx_{sel_class}"]]
    
    st.success(f"📌 {curr_stu['姓名']} ({curr_stu['座號']}號)\n\n性別：{curr_stu['性別']} | 年齡：{curr_stu['年齡']}歲")
    
    st.divider()
    if st.button("🚪 登出", use_container_width=True):
        st.session_state["password_correct"] = False
        st.rerun()

# --- 5. 主介面分頁 ---
tab_entry, tab_ai, tab_manage = st.tabs(["📝 成績錄入", "🚀 AI 智慧診斷", "📊 數據報表與管理"])

# [分頁 1：成績錄入]
with tab_entry:
    col1, col2 = st.columns(2)
    with col1:
        test_cat = st.selectbox("🗂️ 類別", ["一般術科", "體適能", "球類", "田徑"])
        items = df_norms[df_norms["測驗類別"] == test_cat]["項目名稱"].unique().tolist()
        sel_item = st.selectbox("📝 項目", items + ["其他"])
        if sel_item == "其他": sel_item = st.text_input("✍️ 輸入項目名稱")
    with col2:
        fmt = st.selectbox("📏 格式", ["純數字 (次數/分數)", "秒數 (分:秒)", "秒數 (00.00)"])
        if "分:秒" in fmt:
            c1, c2 = st.columns(2)
            final_val = f"{c1.number_input('分',0,20,8):02d}:{c2.number_input('秒',0,59,0):02d}.0"
        elif "00.00" in fmt:
            c1, c2 = st.columns(2)
            final_val = f"{c1.number_input('秒',0,99,13)}.{c2.number_input('毫秒',0,99,0):02d}"
        else: final_val = st.text_input("📊 輸入數值", "0")

    # 計算常模分數
    res_medal, res_score = universal_judge(sel_item, curr_stu['性別'], curr_stu['年齡'], final_val, df_norms)
    
    # 修正點：錄入分頁應存入 Scores 表
    if st.button("💾 儲存成績 (存入 Scores)", use_container_width=True):
        new_score = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "班級": sel_class, "姓名": sel_name, "項目": sel_item,
            "成績": final_val, "等第/獎牌": str(res_score), "備註": res_medal
        }
        old_scores = conn.read(worksheet="Scores").astype(str)
        updated_scores = pd.concat([old_scores, pd.DataFrame([new_score])], ignore_index=True)
        conn.update(worksheet="Scores", data=updated_scores)
        st.success(f"✅ {sel_name} 的數據成績 {res_score} 分已存入！")

    st.divider()
    st.write(f"🕒 **{sel_name} - {sel_item} 近期紀錄：**")
    recent = df_scores[(df_scores['姓名'] == sel_name) & (df_scores['項目'] == sel_item)].copy()
    if not recent.empty:
        display_df = recent[['紀錄時間', '成績', '等第/獎牌']].copy()
        display_df.columns = ['紀錄時間', '原始紀錄(成績)', '數據分數(常模分數)']
        st.dataframe(display_df.tail(5), use_container_width=True)
    else: st.caption("✨ 目前尚無此項目的歷史紀錄")

# [分頁 2：AI 智慧診斷]
with tab_ai:
    score_row = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_item)]
    if score_row.empty:
        st.error(f"❌ 找不到學生【{sel_name}】的數據成績。請先至『成績錄入』完成存檔。"); st.stop()
    
    last_rec = score_row.iloc[-1]
    raw_val = last_rec.get("等第/獎牌")
    data_score = pd.to_numeric(raw_val, errors='coerce')
    
    if pd.isna(data_score):
        st.error(f"🛑 錯誤：【等第/獎牌】欄位無有效分數。"); st.stop()

    c_rows = df_criteria[df_criteria["測驗項目"] == sel_item]
    if c_rows.empty:
        st.error(f"❌ AI_Criteria 表中找不到項目：{sel_item}"); st.stop()
    
    c_row = c_rows.iloc[0]
    w_data, w_tech = parse_logic_weights(str(c_row.get("評分權重 (Scoring_Logic)", "數據(70%), 技術(30%)")))
    indicators = str(c_row.get("具體指標 (Indicators)", ""))
    ai_context = str(c_row.get("AI 指令脈絡 (AI_Context)", "專業體育老師"))
    ai_cues    = str(c_row.get("專業指令與建議 (Cues)", ""))
    unit_str   = str(c_row.get("數據單位 (Data_Unit)", ""))

    col_i, col_v = st.columns([1, 1.2])
    with col_i:
        st.subheader("📊 診斷參考數據")
        st.info(f"👤 學生：{sel_name} | 項目：{sel_item}")
        st.metric("數據得分 (常模轉換)", f"{data_score} 分") 
        st.caption(f"原始紀錄：{last_rec['成績']} {unit_str}")
        st.warning(f"⚖️ 權重：數據 {int(w_data*100)}% / 技術 {int(w_tech*100)}%")
        if indicators: st.info(f"💡 **技術指標：**\n{indicators}")
    
    with col_v:
        st.subheader("📹 動作影像上傳")
        up_v = st.file_uploader("上傳診斷影片", type=["mp4", "mov"])
        if up_v: st.video(up_v)

    st.divider()
    if st.button("🚀 開始執行 AI 綜合診斷", use_container_width=True):
        if not up_v: st.warning("⚠️ 請上傳影片後再執行。")
        else:
            with st.spinner("AI 分析中..."):
                try:
                    temp_path = "temp_analysis.mp4"
                    with open(temp_path, "wb") as f: f.write(up_v.read())
                    video_file = genai.upload_file(path=temp_path)
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2); video_file = genai.get_file(video_file.name)
                    
                    full_prompt = f"""角色：{ai_context}\n項目：{sel_item}\n[第一步：項目偵錯]\n內容不符請回報「🛑 項目偵錯錯誤」。\n[第二步：專業診斷]\n指標：{indicators}\n建議：{ai_cues}\n1.優點 2.缺點 3.建議\n[第三步：評分]\n格式：技術分：XX分。"""
                    model = genai.GenerativeModel(MODEL_ID, generation_config={"temperature": 0})
                    response = model.generate_content([video_file, full_prompt])
                    
                    if "🛑" in response.text: st.error(response.text)
                    else:
                        score_match = re.search(r"技術分：(\d+)", response.text)
                        st.session_state['ai_tech_score'] = int(score_match.group(1)) if score_match else 80
                        st.session_state['ai_report'] = response.text
                        st.session_state['ai_done'] = True
                    genai.delete_file(video_file.name)
                    if os.path.exists(temp_path): os.remove(temp_path)
                except Exception as e: st.error(f"AI 失敗：{e}")

    if st.session_state.get('ai_done'):
        st.markdown("### 📝 AI 專業診斷報告")
        st.info(st.session_state['ai_report'])
        st.divider()
        tech_input = st.number_input(f"核定技術評分 (佔比 {int(w_tech*100)}%)", 0, 100, value=int(st.session_state.get('ai_tech_score', 80)))
        
        # 核心計算公式
        actual_data_w = data_score * w_data
        actual_tech_w = tech_input * w_tech
        total_sum = actual_data_w + actual_tech_w

        st.markdown(f"#### 💡 總分公式：({data_score} × {w_data}) + ({tech_input} × {w_tech})")
        m1, m2, m3 = st.columns(3)
        m1.metric("數據加權", f"{actual_data_w:.1f}")
        m2.metric("技術加權", f"{actual_tech_w:.1f}")
        m3.metric("✅ 最終建議總分", f"{total_sum:.1f}")

        if st.button("💾 確認存入 Analysis_Results", use_container_width=True):
            try:
                new_entry = {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "班級": str(sel_class), "姓名": str(sel_name), "項目": str(sel_item),
                    "數據分數": str(data_score), "技術分數": str(tech_input),
                    "最終修訂分數": str(round(total_sum, 2)),
                    "AI診斷報告": str(st.session_state['ai_report']), "老師評語": "", "老師修正總分": ""
                }
                old_df = conn.read(worksheet="Analysis_Results").astype(str)
                updated_df = pd.concat([old_df, pd.DataFrame([new_entry])], ignore_index=True).drop_duplicates(subset=["姓名", "項目"], keep="last")
                conn.update(worksheet="Analysis_Results", data=updated_df)
                st.success(f"✅ {sel_name} 的紀錄已更新！"); st.balloons()
            except Exception as e: st.error(f"存檔失敗：{e}")

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
