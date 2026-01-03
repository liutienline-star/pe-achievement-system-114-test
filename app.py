import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import re
import os
import time

# --- 1. 頁面初始設定 ---
st.set_page_config(page_title="114學年度體育成績 AI 管理系統", layout="wide", page_icon="🏆")

# API 安全金鑰 (使用 gemini-1.5-flash)
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "gemini-1.5-flash" 
else:
    st.error("❌ 找不到 API_KEY"); st.stop()

# --- 2. 登入權限管理 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True
    st.title("🔒 體育成績管理系統 - 登入")
    col1, _ = st.columns([1, 2])
    with col1:
        u = st.text_input("👤 管理員帳號")
        p = st.text_input("🔑 密碼", type="password")
        if st.button("🚀 確認登入"):
            if u == "tienline" and p == "641101":
                st.session_state["password_correct"] = True
                st.rerun()
            else: st.error("🚫 帳號或密碼錯誤")
    return False

if not check_password(): st.stop()

# --- 3. 資料連線與讀取 (修正：延長快取時間以解決 429 錯誤) ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=600) # 修正：快取改為 10 分鐘，避免頻繁請求 API
def load_full_data():
    try:
        # 修正：移除內部的 ttl="0s"，讓 API 請求頻率降低
        df_sl = conn.read(worksheet="Student_List").astype(str)
        df_s = conn.read(worksheet="Scores").astype(str)
        df_n = conn.read(worksheet="Norms_Settings").astype(str)
        df_c = conn.read(worksheet="AI_Criteria").astype(str)
        try:
            df_h = conn.read(worksheet="Analysis_Results").astype(str)
        except:
            df_h = pd.DataFrame()
        
        # 清理欄位空格與換行
        for df in [df_sl, df_s, df_n, df_c, df_h]:
            if not df.empty:
                df.columns = df.columns.astype(str).str.strip()
        return df_sl, df_s, df_n, df_c, df_h
    except Exception as e:
        st.error(f"資料讀取失敗，可能是 API 限制，請稍候一分鐘再試。詳細錯誤：{e}"); st.stop()

df_student_list, df_scores, df_norms, df_criteria, df_history = load_full_data()

# --- 4. 輔助運算函式 (萬用判定引擎) ---
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

# --- 5. 側邊欄：全域選擇器 ---
with st.sidebar:
    st.header("🏆 系統控制面板")
    
    # 修正：增加手動刷新的按鈕，讓老師在修改 Sheet 後可以手動同步
    if st.button("🔄 強制重新整理資料"):
        st.cache_data.clear()
        st.rerun()

    mode = st.radio("🎯 切換功能模式", ["一般術科與體適能", "🚀 AI 智慧技術診斷", "📊 數據報表與管理"])
    
    st.divider()
    st.header("👤 受測學生選擇")
    df_student_list = df_student_list.map(clean_numeric_string)
    cl_list = sorted(df_student_list['班級'].unique().tolist())
    sel_class = st.selectbox("🏫 選擇班級", cl_list)
    
    stu_df = df_student_list[df_student_list['班級'] == sel_class]
    no_list = stu_df['座號'].sort_values(key=lambda x: pd.to_numeric(x, errors='coerce')).unique()
    sel_no = st.selectbox("🔢 選擇座號", no_list)
    
    # 抓取學生基本資料
    stu = stu_df[stu_df['座號'] == sel_no].iloc[0]
    sel_name = stu['姓名']
    g_col = next((c for c in df_student_list.columns if "性" in c), "性別")
    sel_gender = str(stu[g_col]).strip()
    sel_age = stu.get('年齡', '0')
    
    st.info(f"📌 目前選定：{sel_name}\n\n性別：{sel_gender} | 年齡：{sel_age}歲")
    
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- 6. 主介面邏輯 ---
st.title("🏆 114學年度體育成績管理與 AI 診斷系統")

# [功能一：一般術科與體適能]
if mode == "一般術科與體適能":
    sub_mode = st.radio("📝 紀錄類型", ["一般術科測驗", "體適能測驗"], horizontal=True)
    
    if sub_mode == "一般術科測驗":
        test_cat = st.selectbox("🗂️ 術科類別", ["一般術科", "球類", "田徑", "其他"])
        subject_items = df_norms[df_norms['測驗類別'] != "體適能"]['項目名稱'].unique()
        test_item = st.selectbox("📝 測驗項目", list(subject_items) + ["其他"])
        if test_item == "其他": test_item = st.text_input("✍️ 輸入項目名稱")
        
        col1, col2 = st.columns(2)
        with col1:
            fmt = st.selectbox("📏 格式", ["分數/個數 (純數字)", "秒數 (00.00)"])
            if "秒數" in fmt:
                c1, c2 = st.columns(2)
                final_score = f"{c1.number_input('秒', 0, 99, 13)}.{c2.number_input('毫秒', 0, 99, 0):02d}"
            else: 
                final_score = clean_numeric_string(st.text_input("📊 輸入數值", "0"))
        with col2:
            auto_j = st.checkbox("🤖 自動換算分數", value=True)
            manual_m = st.selectbox("🏅 手動等第", ["優", "甲", "乙", "丙", "丁", "尚未判定"])
            final_medal = universal_judge("一般術科", test_item, sel_gender, 0, final_score, df_norms) if auto_j else manual_m

    else:  # 體適能
        test_cat = "體適能"
        status = st.selectbox("🩺 學生狀態", ["一般生", "身障/重大傷病 (比照銅牌)", "身體羸弱 (比照待加強)"])
        fitness_items = df_norms[df_norms['測驗類別'] == "體適能"]['項目名稱'].unique()
        test_item = st.selectbox("🏃 體適能項目", list(fitness_items))
        if status == "一般生":
            if "跑" in test_item or ":" in str(test_item):
                c1, c2 = st.columns(2)
                final_score, fmt = f"{c1.number_input('分', 0, 20, 8):02d}:{c2.number_input('秒', 0, 59, 0):02d}.0", "秒數 (00:00.0)"
            else:
                val = st.number_input("🔢 數據", 0.0, 500.0, 0.0)
                final_score, fmt = clean_numeric_string(val), "次數/公分"
            final_medal = universal_judge("體適能", test_item, sel_gender, sel_age, final_score, df_norms)
        else:
            final_score, fmt = "N/A", "特殊判定"
            final_medal = ("銅牌" if "身障" in status else "待加強")
    
    note = st.text_input("💬 備註", "")

    st.write("🕒 **近期測驗紀錄：**")
    recent = df_scores[(df_scores['姓名'] == sel_name) & (df_scores['項目'] == test_item)]
    if not recent.empty:
        st.dataframe(recent[['紀錄時間', '成績', '等第/獎牌']].tail(3), use_container_width=True)

    st.divider()
    existing_mask = (df_scores['姓名'] == sel_name) & (df_scores['項目'] == test_item)
    if st.button("💾 儲存成績 (同步更新至雲端)"):
        new_row = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "班級": sel_class, "座號": sel_no, "姓名": sel_name,
            "測驗類別": test_cat, "項目": test_item, "成績": final_score,
            "顯示格式": fmt, "等第/獎牌": final_medal, "備註": note
        }
        df_scores_clean = df_scores.map(clean_numeric_string)
        if existing_mask.any():
            for k, v in new_row.items(): df_scores_clean.loc[existing_mask, k] = str(v)
            final_df = df_scores_clean
        else:
            final_df = pd.concat([df_scores_clean, pd.DataFrame([new_row])], ignore_index=True)
        
        conn.update(worksheet="Scores", data=final_df)
        st.cache_data.clear() # 修正：存檔後清除快取，下次讀取就是新的
        st.balloons(); st.success("✅ 成績已同步更新！"); st.rerun()

# [功能二：AI 智慧技術診斷]
elif mode == "🚀 AI 智慧技術診斷":
    st.subheader(f"🚀 {sel_name} - 動作影像 AI 綜合診斷")
    stu_scores = df_scores[df_scores['姓名'] == sel_name]
    sel_test_ai = st.selectbox("1. 選擇診斷項目", stu_scores['項目'].unique().tolist())
    
    if not sel_test_ai:
        st.warning("請先在『一般術科』模式中錄入該學生的成績數據。")
    else:
        match_criteria = df_criteria[df_criteria["測驗項目"].str.strip() == sel_test_ai.strip()]
        if match_criteria.empty:
            st.error(f"❌ 在 AI_Criteria 中找不到項目：{sel_test_ai}")
        else:
            cri = match_criteria.iloc[0]
            raw_score = stu_scores[stu_scores['項目'] == sel_test_ai].iloc[-1]['成績']
            col_l, col_r = st.columns([1, 1.5])
            with col_l:
                st.metric("實測成績數據", f"{raw_score}")
                st.info(f"📋 性別：{sel_gender}")
                with st.expander("📈 查看參考常模"):
                    st.dataframe(df_norms[df_norms['項目名稱'] == sel_test_ai], hide_index=True)
            with col_r:
                uploaded_v = st.file_uploader("📹 上傳動作影片 (mp4/mov)", type=["mp4", "mov"])
                if uploaded_v: st.video(uploaded_v)
            
            if st.button("🚀 啟動 AI 影像分析"):
                if not uploaded_v: st.warning("請先上傳影片。")
                else:
                    with st.spinner("AI 正在分析影像並計算總分..."):
                        try:
                            temp_path = "temp.mp4"
                            with open(temp_path, "wb") as f: f.write(uploaded_v.read())
                            video_file = genai.upload_file(path=temp_path)
                            while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                            
                            full_prompt = f"""你是一位體育術科評分專家。學生：{sel_name} | 性別：{sel_gender} | 項目：{sel_test_ai} | 數據：{raw_score}
                            【任務要求】1. 性別核對：若不符登記性別({sel_gender})請警示。2. 數據分：根據常模轉換。3. 技術分：指標「{cri.get('Indicators', '')}」。4. 總分：邏輯「{cri.get('Logic', '')}」。5. 處方：建議「{cri.get('Cues', '')}」。"""
                            model = genai.GenerativeModel(MODEL_ID)
                            response = model.generate_content([video_file, full_prompt])
                            st.session_state['ai_report'] = response.text
                            st.session_state['ai_done'] = True
                            genai.delete_file(video_file.name); os.remove(temp_path)
                        except Exception as e: st.error(f"分析失敗：{e}")

            if st.session_state.get('ai_done'):
                st.markdown(st.session_state['ai_report'])
                st.divider()
                st.subheader("👨‍🏫 老師專業校準")
                t_note = st.text_area("給學生的補充評語")
                t_score = st.text_input("修正最終總分 (如不修正請留空)")
                if st.button("💾 存入 Analysis_Results"):
                    new_entry = {"時間": datetime.now().strftime("%Y-%m-%d %H:%M"), "班級": sel_class, "姓名": sel_name, "項目": sel_test_ai, "最終得分": t_score if t_score else "見AI報告", "AI診斷報告": st.session_state['ai_report'], "老師評語": t_note}
                    try:
                        hist = conn.read(worksheet="Analysis_Results")
                        updated = pd.concat([hist, pd.DataFrame([new_entry])], ignore_index=True)
                    except: updated = pd.DataFrame([new_entry])
                    conn.update(worksheet="Analysis_Results", data=updated)
                    st.cache_data.clear() # 修正：存檔成功後清除快取
                    st.success("✅ AI 分析結果已存入雲端！")

# [功能三：數據報表與管理]
elif mode == "📊 數據報表與管理":
    tab1, tab2, tab3 = st.tabs(["👤 個人成績單", "👥 班級總覽", "⚙️ 系統管理"])
    with tab1:
        p_data = df_scores[df_scores['姓名'] == sel_name].copy()
        if not p_data.empty: st.dataframe(p_data, use_container_width=True)
        else: st.info("尚無個人紀錄")
    with tab2:
        cl_data = df_scores[df_scores['班級'] == sel_class].copy()
        if not cl_data.empty:
            st.dataframe(cl_data.sort_values(by='座號'), use_container_width=True)
            csv = cl_data.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載班級報表", csv, f"{sel_class}_report.csv")
        else: st.info("該班尚無紀錄")
    with tab3:
        st.subheader("📝 常模即時編輯")
        edited_norms = st.data_editor(df_norms, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步更新常模"):
            conn.update(worksheet="Norms_Settings", data=edited_norms)
            st.cache_data.clear()
            st.success("常模已更新！"); st.rerun()
        st.divider()
        st.subheader("🛠️ 全校重新判定工具")
        if st.button("🚀 依照新常模重算全校分數"):
            with st.spinner("重算中..."):
                stu_info = df_student_list.set_index('姓名')[['性別', '年齡']].to_dict('index')
                for idx, row in df_scores.iterrows():
                    if row['姓名'] in stu_info:
                        s = stu_info[row['姓名']]
                        cat = "體適能" if row['測驗類別'] == "體適能" else "一般術科"
                        df_scores.at[idx, '等第/獎牌'] = universal_judge(cat, row['項目'], s['性別'], s['年齡'], row['成績'], df_norms)
                conn.update(worksheet="Scores", data=df_scores.map(clean_numeric_string))
                st.cache_data.clear()
                st.success("全校成績重算完成！"); st.rerun()
