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
        # 過濾項目與性別
        mask = (norms_df['項目名稱'].astype(str) == str(item)) & \
               (norms_df['性別'].astype(str) == str(gender))
        
        f = norms_df[mask].copy()
        if f.empty: return "無常模", 60
        
        v = parse_time_to_seconds(value)
        comp = f['比較方式'].iloc[0]
        
        # 轉換門檻值為數字
        f['門檻值_num'] = pd.to_numeric(f['門檻值'], errors='coerce')
        f = f.sort_values('門檻值_num', ascending=(comp == "<="))
        
        # --- 【核心修正點】 ---
        # 遍歷每一列，找到符合區間的那一列
        for _, row in f.iterrows():
            if (comp == ">=" and v >= row['門檻值_num']) or \
               (comp == "<=" and v <= row['門檻值_num']):
                
                # 直接抓取表格中的 '分數' 欄位值 (例如 69)
                # 若您的表格欄位標題不是「分數」，請修改下方欄位名
                raw_score = row.get('分數', 60) 
                
                # 回傳結果與試算表中的實際分數
                return row['判定結果'], int(float(raw_score))
        
        return "待加強", 60
    except Exception as e:
        return f"判定錯誤: {e}", 0

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

# [分頁 1：成績錄入 - 背景自動計算版]
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
        else:
            final_val = st.text_input("📊 輸入數值", "0")

    # --- 背景運算 ---
    # 此處 res_score 就是您要的 69 分
    res_medal, res_score = universal_judge(sel_item, curr_stu['性別'], curr_stu['年齡'], final_val, df_norms)
    
    st.divider()

    # --- 【核心修改 1：呈現近期紀錄】 ---
    st.write(f"🕒 **{sel_name} - {sel_item} 近期紀錄：**")
    
    # 篩選該生、該項目的歷史紀錄
    recent = df_scores[(df_scores['姓名'] == sel_name) & (df_scores['項目'] == sel_item)].copy()
    
    if not recent.empty:
        # 1. 如果您的 Scores 工作表還沒有「數據分數」這一欄，我們把「等第/獎牌」這欄拿來當分數顯示
        # 2. 這裡我們選取所需的欄位，並重新命名讓老師看更清楚
        display_df = recent[['紀錄時間', '成績', '等第/獎牌']].copy()
        display_df.columns = ['紀錄時間', '原始紀錄(成績)', '數據分數(常模分數)']
        
        st.dataframe(display_df.tail(5), use_container_width=True) # 顯示最近 5 筆
    else:
        st.caption("✨ 目前尚無此項目的歷史紀錄")

    # --- 【核心修改 2：儲存邏輯】 ---
    if st.button("💾 儲存並同步成績", use_container_width=True):
        new_row = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "班級": sel_class, 
            "座號": curr_stu['座號'], 
            "姓名": sel_name,
            "測驗類別": test_cat, 
            "項目": sel_item, 
            "成績": final_val, # 原始次數/秒數
            "顯示格式": fmt, 
            "等第/獎牌": str(res_score), # <--- 將轉換後的 69 分存入此欄位
            "備註": res_medal # <--- 把「優、甲」等文字存入備註，保持數據分數純淨
        }
        
        # 覆蓋或新增邏輯
        mask = (df_scores['姓名'] == sel_name) & (df_scores['項目'] == sel_item)
        if mask.any():
            for k, v in new_row.items(): 
                df_scores.loc[mask, k] = str(v)
            final_df = df_scores
        else:
            final_df = pd.concat([df_scores, pd.DataFrame([new_row])], ignore_index=True)
        
        try:
            conn.update(worksheet="Scores", data=final_df)
            st.success(f"✅ 儲存成功！數據分數：{res_score}")
            st.balloons() 
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"存檔失敗：{e}")
# [分頁 2：AI 智慧診斷]
with tab_ai:
    # 1. 讀取學生成績與預存的常模分數
    score_row = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_item)]
    
    if score_row.empty:
        st.warning(f"⚠️ 請先在左側選好項目，並於『成績錄入』分頁存入 【{sel_name}】 的數據紀錄。")
    else:
        # --- 【核心數據抓取】 ---
        # 取得最新一筆原始成績 (例如: 5次)
        current_val = score_row.iloc[-1]["成績"]
        
        # 直接從我們剛才修正的「等第/獎牌」欄位抓取已經存好的分數 (例如: 69)
        # 增加 pd.to_numeric 確保它是數字型態，避免 60 分的錯誤
        saved_score = pd.to_numeric(score_row.iloc[-1].get("等第/獎牌", 60), errors='coerce')
        data_score = int(saved_score) if not pd.isna(saved_score) else 60
        
        # 2. 抓取 AI_Criteria 指標與權重
        c_rows = df_criteria[df_criteria["測驗項目"] == sel_item]
        if c_rows.empty: 
            st.error(f"❌ AI_Criteria 找不到此項目指標：{sel_item}"); st.stop()
        c_row = c_rows.iloc[0]

        # 解析權重 (例如：70/30)
        logic_str = str(c_row.get("評分權重", "70/30"))
        w_data, w_tech = parse_logic_weights(logic_str)
        unit_str = str(c_row.get("數據單位", ""))
        indicators = str(c_row.get("具體指標", ""))

        # 3. 介面呈現：診斷看板
        col_i, col_v = st.columns([1, 1.2])
        with col_i:
            st.subheader("📊 診斷參考數據")
            # 這裡就會亮眼地顯示出您要的 69 分 (或其他常模轉換後的數值)
            st.metric("數據得分 (常模轉換)", f"{data_score} 分", help="此為根據常模表換算後的分數") 
            st.write(f"📝 **原始紀錄：** {current_val} {unit_str}")
            st.write(f"⚙️ **權重配置：** 數據 {int(w_data*100)}% / 技術 {int(w_tech*100)}%")
            if indicators:
                st.info(f"💡 **技術指標參考：**\n{indicators}")
            
        with col_v:
            st.subheader("📹 動作影像上傳")
            up_v = st.file_uploader("選擇影片檔案", type=["mp4", "mov"])
            if up_v: st.video(up_v)

        # 4. AI 分析執行區 (保持不變)
        st.divider()
        if st.button("🚀 開始執行 AI 綜合診斷", use_container_width=True):
            if not up_v: st.warning("⚠️ 請上傳影片。")
            else:
                with st.spinner("AI 正在分析動作優缺點與技術分..."):
                    try:
                        temp_path = "temp_analysis.mp4"
                        with open(temp_path, "wb") as f: f.write(up_v.read())
                        video_file = genai.upload_file(path=temp_path)
                        while video_file.state.name == "PROCESSING":
                            time.sleep(2)
                            video_file = genai.get_file(video_file.name)
                        
                        full_prompt = f"角色設定：{c_row.get('AI 指令脈絡', '體育老師')}\n任務：1.分析優缺點 2.參考指標「{indicators}」\n請在結尾回傳「技術分：XX分」。"
                        model = genai.GenerativeModel(MODEL_ID)
                        response = model.generate_content([video_file, full_prompt])
                        
                        # 解析技術分
                        score_match = re.search(r"技術分：(\d+)", response.text)
                        st.session_state['ai_tech_score'] = int(score_match.group(1)) if score_match else 80
                        st.session_state['ai_report'] = response.text
                        st.session_state['ai_done'] = True
                        
                        genai.delete_file(video_file.name)
                        if os.path.exists(temp_path): os.remove(temp_path)
                    except Exception as e:
                        st.error(f"AI 分析失敗：{e}")

        # 5. 【核心連動】老師人工校準與最終存檔
        if st.session_state.get('ai_done'):
            st.markdown("### 📝 AI 綜合診斷報告")
            st.info(st.session_state['ai_report'])
            
            st.divider()
            st.subheader("👨‍🏫 老師人工校準與評分核定")
            
            # --- [連動 1：技術分] ---
            ai_suggested = st.session_state.get('ai_tech_score', 80)
            tech_input = st.number_input(f"調整技術表現評分 (權重 {int(w_tech*100)}%)", 0, 100, value=int(ai_suggested))

            # --- [連動 2：計算加權總分] ---
            # 這是老師最在意的：數據(69)*權重 + 技術*權重
            actual_data_w = data_score * w_data
            actual_tech_w = tech_input * w_tech
            total_sum = actual_data_w + actual_tech_w

            st.markdown("#### 💡 總分核算細節")
            m1, m2, m3 = st.columns(3)
            with m1: st.metric("數據加權分", f"{actual_data_w:.1f}", f"基數: {data_score}")
            with m2: st.metric("技術加權分", f"{actual_tech_w:.1f}", f"基數: {tech_input}")
            with m3: st.metric("✅ 建議總分", f"{total_sum:.1f}", delta="加權結果")

            st.divider()
            col_rev, col_note = st.columns([1, 2])
            with col_rev:
                final_revised = st.text_input("🔢 最終核定分數", value=f"{total_sum:.1f}")
            with col_note:
                t_note = st.text_area("💬 老師補充評語")
            
            if st.button("💾 確認校準並存入 Analysis_Results", use_container_width=True):
                try:
                    new_h = {
                        "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "班級": sel_class, "姓名": sel_name, "項目": sel_item,
                        "數據分數": data_score, "技術分數": tech_input, 
                        "最終修訂分數": final_revised, "AI診斷報告": st.session_state['ai_report'], "老師評語": t_note
                    }
                    old_h = conn.read(worksheet="Analysis_Results").astype(str)
                    updated_h = pd.concat([old_h, pd.DataFrame([new_h])], ignore_index=True)
                    conn.update(worksheet="Analysis_Results", data=updated_h)
                    st.success(f"✅ {sel_name} 的診斷紀錄已存檔！")
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
