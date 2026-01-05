import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import os, time, re

# --- 1. 系統初始與安全性設定 ---
st.set_page_config(page_title="114學年度體育 AI 智慧診斷平台", layout="wide", page_icon="🤖")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "gemini-2.0-flash" 
else:
    st.error("❌ 找不到 API_KEY，請在 Streamlit Secrets 設定。"); st.stop()

# --- 2. 核心資料工具與讀取 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def clean_data(df):
    return df.astype(str).map(lambda x: x.strip() if pd.notna(x) and x != 'nan' else "")

@st.cache_data(ttl=300)
def load_all_data():
    try:
        student_list = clean_data(conn.read(worksheet="Student_List"))
        ai_criteria = clean_data(conn.read(worksheet="AI_Criteria"))
        scores_data = clean_data(conn.read(worksheet="Scores"))
        try:
            analysis_results = clean_data(conn.read(worksheet="Analysis_Results"))
        except:
            analysis_results = pd.DataFrame(columns=["時間", "班級", "座號", "姓名", "項目", "數據分數", "技術分數", "最終得分", "AI診斷報告"])
        return student_list, ai_criteria, scores_data, analysis_results
    except Exception as e:
        st.error(f"讀取失敗：{e}"); st.stop()

df_students, df_criteria, df_scores, df_history = load_all_data()

# --- 3. 側邊欄：學生選單 ---
with st.sidebar:
    st.header("👤 診斷對象")
    all_classes = sorted(df_students["班級"].unique())
    sel_class = st.selectbox("1. 選擇班級", all_classes)
    
    stu_df = df_students[df_students["班級"] == sel_class].copy()
    stu_df["座號_int"] = pd.to_numeric(stu_df["座號"], errors="coerce")
    stu_df = stu_df.sort_values("座號_int")
    
    stu_options = [f"[{row['座號']}] {row['姓名']}" for _, row in stu_df.iterrows()]
    sel_option = st.selectbox("2. 選擇學生", stu_options)
    sel_name = re.search(r"\] (.*)", sel_option).group(1)
    curr_stu = stu_df[stu_df["姓名"] == sel_name].iloc[0]
    
    st.divider()
    if st.button("🔄 重新整理雲端資料"):
        st.cache_data.clear(); st.rerun()

# --- 4. 主介面：AI 診斷核心 ---
st.title("🚀 體育技術 AI 精準診斷系統")

col_config, col_raw = st.columns([1, 1.2])

with col_config:
    st.subheader("🎯 1. 診斷規準確認")
    available_items = df_criteria["測驗項目"].unique()
    sel_item = st.selectbox("選擇診斷項目", available_items)
    
    c_row = df_criteria[df_criteria["測驗項目"] == sel_item].iloc[0]
    indicators = c_row.get("具體指標 (Indicators)", "未設定指標")
    
    # 權重解析
    weights = re.findall(r"(\d+)", str(c_row.get("評分權重 (Scoring_Logic)", "70,30")))
    w_data = int(weights[0])/100 if len(weights) >= 2 else 0.7
    w_tech = int(weights[1])/100 if len(weights) >= 2 else 0.3
    
    with st.expander("📝 本項技術指標詳情"):
        st.info(f"AI 將嚴格對照下列指標進行偵錯與評分：\n\n{indicators}")

with col_raw:
    st.subheader("📊 2. 原始數據檢索")
    match_score = df_scores[
        (df_scores["姓名"].str.strip() == sel_name.strip()) & 
        (df_scores["項目"].str.strip() == sel_item.strip())
    ]
    
    if not match_score.empty:
        last_rec = match_score.iloc[-1]
        data_score = pd.to_numeric(last_rec.get("等第/獎牌", 0), errors='coerce')
        st.success(f"✅ 已對接 Scores 分頁：{sel_name} / {sel_item}")
        st.metric("原始數據分數", f"{data_score} 分", f"權重佔比 {int(w_data*100)}%")
    else:
        st.warning("⚠️ 找不到原始成績紀錄")
        data_score = st.number_input("手動補錄數據分", 0, 100, 0)

st.divider()

col_video, col_report = st.columns([1, 1.2])

with col_video:
    st.subheader("📹 3. 動作影像上傳")
    up_v = st.file_uploader(f"請上傳【{sel_item}】教學影片", type=["mp4", "mov"])
    if up_v: st.video(up_v)

with col_report:
    st.subheader("📝 4. AI 深度診斷報告")
    
    if st.button("🚀 啟動 AI 指標對照分析", use_container_width=True) and up_v:
        with st.spinner("AI 考官正在逐幀比對技術指標..."):
            try:
                temp_fn = f"temp_{int(time.time())}.mp4"
                with open(temp_fn, "wb") as f: f.write(up_v.read())
                
                v_file = genai.upload_file(path=temp_fn)
                while v_file.state.name == "PROCESSING":
                    time.sleep(2); v_file = genai.get_file(v_file.name)
                
                # --- 核心強化 Prompt (加入指標比對偵錯) ---
                full_prompt = f"""
                你是最高級別體育考官，目前正在進行【{sel_item}】的技術鑑定。
                技術指標定義："{indicators}"

                ### 第一階段：視覺指標偵錯 (🛑)
                1. 檢查影片內容是否為【{sel_item}】。
                2. 【核心要求】：逐一比對影片動作是否包含技術指標："{indicators}"。
                3. 若影片內容與指標完全不符，或並未展現相關技術動作，請立即回報：
                   🛑 項目偵錯錯誤。
                   理由：[說明為何影片動作不符合具體指標要求]。
                4. 若通過指標初步比對，才進行後續分析。

                ### 第二階段：專業技術分析
                根據脈絡：{c_row.get('AI 指令脈絡 (AI_Context)', '教學診斷')}
                提供：[確認動作優點]、[關鍵改進點]、[針對指標的優化建議]。

                ### 第三階段：技術評分 (⚠️ 必須嚴格遵守指標比對結果)
                評分階梯：
                - 【完全達成】：90-100 分 (指標動作精準且穩定)
                - 【部分達成】：80-89 分 (具備指標動作但細節不周)
                - 【基礎達成】：75-79 分 (僅具備雛形，指標達成率低)
                - 【未達標】：70 分以下 (動作與指標要求嚴重背離)

                格式要求：
                最後請務必以「技術分：[數字]」結尾。
                """
                
                model = genai.GenerativeModel(MODEL_ID)
                response = model.generate_content([v_file, full_prompt])
                
                st.session_state['report_text'] = response.text
                score_match = re.search(r"技術分：(\d+)", response.text)
                st.session_state['tech_score'] = int(score_match.group(1)) if score_match else 70
                st.session_state['done'] = True
                
                genai.delete_file(v_file.name)
                if os.path.exists(temp_fn): os.remove(temp_fn)
            except Exception as e: st.error(f"分析失敗：{e}")

    if st.session_state.get('done'):
        st.markdown(st.session_state['report_text'])
        
        # 只有在沒報錯的情況下才顯示分數與存檔按鈕
        if "🛑" not in st.session_state['report_text']:
            t_score = st.session_state['tech_score']
            final_total = (data_score * w_data) + (t_score * w_tech)
            
            st.divider()
            st.metric("🏆 最終綜合判定", f"{final_total:.1f} 分", f"技術分：{t_score}")
            
            if st.button("💾 將診斷結果存入雲端", use_container_width=True):
                new_res = {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"), "班級": sel_class, "座號": curr_stu['座號'],
                    "姓名": sel_name, "項目": sel_item, "數據分數": str(data_score),
                    "技術分數": str(t_score), "最終得分": str(round(final_total, 2)),
                    "AI診斷報告": st.session_state['report_text'].replace("\n", " ")
                }
                df_history = pd.concat([df_history, pd.DataFrame([new_res])], ignore_index=True).drop_duplicates(subset=["姓名", "項目"], keep="last")
                conn.update(worksheet="Analysis_Results", data=df_history)
                st.success("✅ 紀錄已成功更新！")
        else:
            st.error("⚠️ 影像內容與指標不符，請重新拍攝正確的技術動作影片。")
