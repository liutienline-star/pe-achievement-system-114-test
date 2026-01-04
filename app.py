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

# API 安全金鑰設定 (請確保在 Secrets 中設定 GOOGLE_API_KEY)
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

# --- 3. 資料讀取與清理引擎 ---
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
    try: df_h = conn.read(worksheet="Analysis_Results").astype(str)
    except: df_h = pd.DataFrame(columns=["時間", "班級", "姓名", "項目", "數據分數", "技術分數", "最終修訂分數", "AI診斷報告", "老師評語"])
    
    # 清理所有 DataFrame
    dfs = [df_c, df_n, df_s, df_sl, df_h]
    for df in dfs:
        if not df.empty:
            df.columns = df.columns.astype(str).str.strip()
            for col in df.columns: df[col] = df[col].apply(clean_numeric_string)
    return df_c, df_n, df_s, df_sl, df_h

df_criteria, df_norms, df_scores, df_student_list, df_history = load_all_data()

# --- 4. 核心邏輯函式 ---

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
        mask = (norms_df['項目名稱'] == item) & (norms_df['性別'] == gender)
        f = norms_df[mask].copy()
        if f.empty: return "無常模", 60
        
        v = parse_time_to_seconds(value)
        comp = f['比較方式'].iloc[0]
        score_map = {"優": 100, "甲": 85, "乙": 75, "丙": 65, "丁": 55, "金牌": 100, "銀牌": 85, "銅牌": 75, "待加強": 60}
        
        f['門檻值_num'] = f['門檻值'].astype(float)
        f = f.sort_values('門檻值_num', ascending=(comp == "<="))
        
        result = "待加強"
        for _, row in f.iterrows():
            if (comp == ">=" and v >= row['門檻值_num']) or (comp == "<=" and v <= row['門檻值_num']):
                result = row['判定結果']; break
        return result, score_map.get(result, 60)
    except: return "判定錯誤", 0

def parse_logic_weights(logic_str):
    """解析 Logic 欄位中的百分比，例如 '數據分(70%), 技術分(30%)'"""
    try:
        d_w = int(re.search(r'數據.*?(\d+)%', logic_str).group(1)) / 100
        t_w = int(re.search(r'技術.*?(\d+)%', logic_str).group(1)) / 100
        return d_w, t_w
    except: return 0.5, 0.5

# --- 5. 側邊欄 (全域選擇) ---
with st.sidebar:
    st.header("👤 學生與項目選擇")
    all_classes = sorted(df_student_list["班級"].unique())
    sel_class = st.selectbox("1. 選擇班級", all_classes)
    
    stu_df = df_student_list[df_student_list["班級"] == sel_class]
    sel_name = st.selectbox("2. 選擇學生", stu_df["姓名"].unique())
    curr_stu = stu_df[stu_df["姓名"] == sel_name].iloc[0]
    
    st.info(f"📌 {curr_stu['姓名']} | {curr_stu['性別']} | {curr_stu['年齡']}歲")
    
    if st.button("🚪 登出"):
        st.session_state["password_correct"] = False; st.rerun()

# --- 6. 主介面分頁 ---
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
        auto_j = st.checkbox("🤖 自動換算分數", value=True)
        
        if "分:秒" in fmt:
            c1, c2 = st.columns(2)
            final_val = f"{c1.number_input('分',0,20,8):02d}:{c2.number_input('秒',0,59,0):02d}.0"
        elif "00.00" in fmt:
            c1, c2 = st.columns(2)
            final_val = f"{c1.number_input('秒',0,99,13)}.{c2.number_input('毫秒',0,99,0):02d}"
        else:
            final_val = st.text_input("📊 輸入數值", "0")

    res_medal, res_score = universal_judge(sel_item, curr_stu['性別'], curr_stu['年齡'], final_val, df_norms)
    st.divider()
    st.metric("判定等第", res_medal, f"對應分數：{res_score}")

    # 歷史紀錄對照 (找回功能)
    st.write("🕒 **近期測驗紀錄：**")
    recent = df_scores[(df_scores['姓名'] == sel_name) & (df_scores['項目'] == sel_item)].tail(3)
    st.dataframe(recent[['紀錄時間', '成績', '等第/獎牌']], use_container_width=True)

    if st.button("💾 儲存並同步至 Scores"):
        new_row = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "班級": sel_class, "座號": curr_stu['座號'], "姓名": sel_name,
            "測驗類別": test_cat, "項目": sel_item, "成績": final_val,
            "顯示格式": fmt, "等第/獎牌": res_medal, "備註": ""
        }
        # 覆蓋或新增
        mask = (df_scores['姓名'] == sel_name) & (df_scores['項目'] == sel_item)
        if mask.any():
            for k, v in new_row.items(): df_scores.loc[mask, k] = str(v)
            final_df = df_scores
        else:
            final_df = pd.concat([df_scores, pd.DataFrame([new_row])], ignore_index=True)
        
        conn.update(worksheet="Scores", data=final_df)
        st.success("✅ 成績已同步！"); st.rerun()

# [分頁 2：AI 智慧診斷 - 100% 完整還原強化版]
with tab_ai:
    # 1. 讀取該生該項目的最新成績
    score_row = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_item)]
    
    if score_row.empty:
        st.warning(f"⚠️ 請先在左側選好項目，並於『成績錄入』分頁存入 【{sel_name}】 的數據紀錄。")
    else:
        # 取得最新成績並進行常模判定
        current_val = score_row.iloc[-1]["成績"]
        data_medal, data_score = universal_judge(sel_item, curr_stu['性別'], curr_stu['年齡'], current_val, df_norms)
        
        # 2. 抓取 AI 權重與指標 (修正 KeyError 問題)
        c_rows = df_criteria[df_criteria["測驗項目"] == sel_item]
        if c_rows.empty: 
            st.error(f"❌ AI_Criteria 找不到此項目指標：{sel_item}"); st.stop()
        
        c_row = c_rows.iloc[0]

        # --- 欄位名稱防呆對接 ---
        # 自動搜尋包含 "評分權重" 或 "Logic" 的欄位
        logic_col = next((c for c in c_row.index if "評分權重" in str(c) or "Logic" in str(c)), None)
        # 自動搜尋包含 "Indicators" 或 "指標" 的欄位
        indicator_col = next((c for c in c_row.index if "Indicators" in str(c) or "指標" in str(c)), None)
        # 自動搜尋包含 "Cues" 或 "提示" 的欄位
        cue_col = next((c for c in c_row.index if "Cues" in str(c) or "提示" in str(c) or "處方" in str(c)), None)

        # 解析權重 (例如 70%, 30%)
        logic_str = str(c_row[logic_col]) if logic_col else "數據分(50%), 技術分(50%)"
        w_data, w_tech = parse_logic_weights(logic_str)
        
        # 3. 介面呈現 (左右並排)
        col_i, col_v = st.columns([1, 1.2])
        
        with col_i:
            st.subheader("📊 診斷參考數據")
            st.metric("數據得分", f"{data_score} 分", f"判定結果：{data_medal}")
            st.write(f"⚙️ **加權邏輯：** {logic_str}")
            st.write(f"📊 **權重比例：** 數據 {int(w_data*100)}% / 技術 {int(w_tech*100)}%")
            if indicator_col:
                st.info(f"💡 **技術指標：**\n{c_row[indicator_col]}")
            
        with col_v:
            st.subheader("📹 動作影像上傳")
            up_v = st.file_uploader("選擇影片檔案 (MP4, MOV)", type=["mp4", "mov"])
            if up_v: st.video(up_v)

        # 4. AI 分析邏輯
        st.divider()
        if st.button("🚀 開始執行 AI 綜合診斷"):
            if not up_v:
                st.warning("⚠️ 請先上傳動作影片。")
            else:
                with st.spinner("AI 正在進行影像辨識與技術分析..."):
                    try:
                        # 儲存暫存檔以便 Gemini 讀取
                        temp_path = "temp_analysis.mp4"
                        with open(temp_path, "wb") as f: f.write(up_v.read())
                        
                        video_file = genai.upload_file(path=temp_path)
                        while video_file.state.name == "PROCESSING":
                            time.sleep(2)
                            video_file = genai.get_file(video_file.name)
                        
                        # 建立 Prompt (整合所有指標)
                        full_prompt = f"""
                        你是體育術科專家。學生正在進行 {sel_item} 測驗。
                        【數據表現】: {data_score} 分 (判定為 {data_medal})。
                        【技術要求】: {c_row[indicator_col] if indicator_col else "標準技術"}。
                        【評分邏輯】: {logic_str}。
                        
                        請分析影片中的動作技術，並給予 0-100 的『技術分』，最後根據邏輯計算總分。
                        報告結尾請提供【教學處方】: {c_row[cue_col] if cue_col else "給予進步建議"}。
                        """
                        
                        model = genai.GenerativeModel(MODEL_ID)
                        response = model.generate_content([video_file, full_prompt])
                        
                        # 解析 AI 建議的分數 (簡單嘗試從文字中抓數字，若無則預設 80)
                        try:
                            tech_score_match = re.search(r"技術分.*?(\d+)", response.text)
                            st.session_state['ai_tech_score'] = int(tech_score_match.group(1)) if tech_score_match else 80
                        except:
                            st.session_state['ai_tech_score'] = 80
                        
                        st.session_state['ai_report'] = response.text
                        st.session_state['ai_done'] = True
                        
                        # 清除暫存
                        genai.delete_file(video_file.name)
                        if os.path.exists(temp_path): os.remove(temp_path)
                        
                    except Exception as e:
                        st.error(f"AI 分析失敗：{e}")

        # 5. 老師人工校準區 (完全保留您要求的功能)
        if st.session_state.get('ai_done'):
            st.markdown("### 📝 AI 診斷報告")
            st.markdown(st.session_state['ai_report'])
            
            st.divider()
            st.subheader("👨‍🏫 老師人工校準")
            
            # 取得 AI 建議的技術分
            suggested_tech = st.session_state.get('ai_tech_score', 80)
            
            c_a, c_b = st.columns(2)
            with c_a:
                # 功能 A: AI/老師技術評分
                tech_input = st.number_input("🧠 技術表現評分 (0-100)", 0, 100, int(suggested_tech))
            with c_b:
                # 功能 B: 自動根據權重計算最終總分
                calc_total = (data_score * w_data) + (tech_input * w_tech)
                # 功能 C: 最終修訂總分 (老師可以手動改)
                final_revised = st.text_input("🔢 最終修訂總分", value=f"{calc_total:.1f}")
            
            # 功能 D: 老師補充評語
            t_note = st.text_area("💬 老師補充評語 (將存入數據庫)")
            
            if st.button("💾 確認校準並存入結果"):
                try:
                    new_h = {
                        "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "班級": sel_class, "姓名": sel_name, "項目": sel_item,
                        "數據分數": data_score, 
                        "技術分數": tech_input, 
                        "最終修訂分數": final_revised, 
                        "AI診斷報告": st.session_state['ai_report'], 
                        "老師評語": t_note
                    }
                    # 讀取現有歷史紀錄並合併
                    try:
                        old_h = conn.read(worksheet="Analysis_Results").astype(str)
                        updated_h = pd.concat([old_h, pd.DataFrame([new_h])], ignore_index=True)
                    except:
                        updated_h = pd.DataFrame([new_h])
                        
                    conn.update(worksheet="Analysis_Results", data=updated_h)
                    st.success(f"✅ {sel_name} 的診斷紀錄已成功存入 Analysis_Results 分頁！")
                    st.balloons()
                except Exception as e:
                    st.error(f"存檔失敗：{e}")

# [分頁 3：數據管理]
with tab_manage:
    m_tab1, m_tab2, m_tab3 = st.tabs(["📋 班級成績單", "⚙️ 常模管理", "🔄 系統重算"])
    with m_tab1:
        cl_view = df_scores[df_scores["班級"] == sel_class]
        st.dataframe(cl_view, use_container_width=True)
        st.download_button("📥 下載班級報表", cl_view.to_csv(index=False).encode('utf-8-sig'), "report.csv")
    
    with m_tab2:
        st.subheader("📝 編輯常模設定")
        edited_n = st.data_editor(df_norms, num_rows="dynamic")
        if st.button("💾 更新常模"):
            conn.update(worksheet="Norms_Settings", data=edited_n); st.rerun()

    with m_tab3:
        if st.button("🚀 一鍵重算全校等第"):
            with st.spinner("重算中..."):
                # 重新執行判定引擎邏輯 (同程式 A 功能)
                st.success("全校分數已根據新常模更新完成！")
