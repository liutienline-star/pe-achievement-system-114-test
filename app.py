import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import os, time, re

# --- 1. 系統初始設定 ---
st.set_page_config(page_title="AI 體育智慧診斷平台", layout="wide", page_icon="🏅")

# 自定義 CSS 讓介面更美觀
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .report-card { background-color: #ffffff; padding: 20px; border-radius: 10px; border-left: 5px solid #007bff; }
    </style>
    """, unsafe_allow_html=True)

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "gemini-2.0-flash" 
else:
    st.error("❌ 找不到 API_KEY，請在 Streamlit Secrets 設定。"); st.stop()

# --- 2. 核心資料讀取與格式化 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def clean_data(df):
    """清洗資料並處理數字格式，防止出現 .0"""
    df = df.astype(str).map(lambda x: x.strip() if pd.notna(x) and x != 'nan' else "")
    # 針對可能是數字的欄位進行去小數處理
    for col in ['班級', '座號', '等第/獎牌']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: x.split('.')[0] if '.' in x else x)
    return df

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
        st.error(f"📡 資料連結失敗：{e}"); st.stop()

df_students, df_criteria, df_scores, df_history = load_all_data()

# --- 3. 側邊欄：導航控制 ---
with st.sidebar:
    st.title("📂 學生檔案箱")
    all_classes = sorted(df_students["班級"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
    sel_class = st.selectbox("🏫 選擇班級", all_classes)
    
    # 過濾並排序座號
    stu_df = df_students[df_students["班級"] == sel_class].copy()
    stu_df["座號_int"] = pd.to_numeric(stu_df["座號"], errors="coerce").fillna(0).astype(int)
    stu_df = stu_df.sort_values("座號_int")
    
    # 組合學生選項 (避免 .0)
    stu_options = [f"【 {int(row['座號'])}】{row['姓名']}" for _, row in stu_df.iterrows()]
    sel_option = st.selectbox("👤 選擇學生", stu_options)
    
    # 提取純姓名
    sel_name = re.search(r"】(.*)", sel_option).group(1)
    curr_stu = stu_df[stu_df["姓名"] == sel_name].iloc[0]
    
    st.divider()
    st.markdown(f"**當前診斷對象**：\n### {sel_name} ({curr_stu['性別']})")
    if st.button("🔄 同步雲端數據"):
        st.cache_data.clear(); st.rerun()

# --- 4. 主介面：核心診斷儀表板 ---
st.title("🏆 AI 體育技術精準診斷系統")

# 第一區：項目與數據
with st.container():
    c1, c2 = st.columns([1, 1])
    
    with c1:
        st.subheader("🎯 1. 診斷設定")
        available_items = df_criteria["測驗項目"].unique()
        sel_item = st.selectbox("請選擇測驗項目", available_items)
        
        c_row = df_criteria[df_criteria["測驗項目"] == sel_item].iloc[0]
        indicators = c_row.get("具體指標 (Indicators)", "未設定指標")
        
        # 權重解析：確保不會出現 1%
        weights = re.findall(r"(\d+)", str(c_row.get("評分權重 (Scoring_Logic)", "70,30")))
        w_data_pct = int(weights[0]) if len(weights) >= 2 else 70
        w_tech_pct = int(weights[1]) if len(weights) >= 2 else 30
        w_data = w_data_pct / 100
        w_tech = w_tech_pct / 100

    with c2:
        st.subheader("📊 2. 原始成績檢索")
        match_score = df_scores[
            (df_scores["姓名"].str.strip() == sel_name.strip()) & 
            (df_scores["項目"].str.strip() == sel_item.strip())
        ]
        
        if not match_score.empty:
            last_rec = match_score.iloc[-1]
            raw_record = last_rec.get("成績", "無紀錄") # 原始數據 (如 12.5秒)
            data_points = pd.to_numeric(last_rec.get("等第/獎牌", 0), errors='coerce') # 轉換後的點數
            
            st.info(f"✅ 已對接 Scores 分頁成績")
            col_a, col_b = st.columns(2)
            col_a.metric("原始測驗紀錄", f"{raw_record}")
            col_b.metric("數據轉化分數", f"{int(data_points)} 分")
        else:
            st.warning("⚠️ 查無成績，請手動輸入分數")
            data_points = st.number_input("手動數據分", 0, 100, 0)

# 第二區：影像與診斷
st.divider()
v_col, r_col = st.columns([1, 1.2])

with v_col:
    st.subheader("📹 3. 動作影像上傳")
    up_v = st.file_uploader(f"📎 上傳【{sel_item}】動作影片", type=["mp4", "mov"])
    if up_v:
        st.video(up_v)
        with st.expander("📝 查看評分指標規準"):
            st.write(f"**AI 診斷重點：**\n{indicators}")

with r_col:
    st.subheader("📝 4. AI 專業診斷報告")
    
    if st.button("🚀 啟動 AI 指標對照分析", use_container_width=True) and up_v:
        with st.spinner("AI 考官正在分析動作細節..."):
            try:
                temp_fn = f"temp_{int(time.time())}.mp4"
                with open(temp_fn, "wb") as f: f.write(up_v.read())
                
                v_file = genai.upload_file(path=temp_fn)
                while v_file.state.name == "PROCESSING":
                    time.sleep(2); v_file = genai.get_file(v_file.name)
                
                full_prompt = f"""
                你是體育考官，進行【{sel_item}】鑑定。
                技術指標："{indicators}"

                ### 第一階段：視覺指標偵錯 (🛑)
                1. 比對影片是否符合指標："{indicators}"。
                2. 若不符，回報：🛑 項目偵錯錯誤。理由：[說明不符原因]。

                ### 第二階段：專業診斷
                提供：[動作優點]、[改進關鍵點]、[練習處方]。

                ### 第三階段：技術評分 (嚴格對照指標)
                - 完全達成：90-100 | 部分達成：80-89 | 基礎達成：75-79 | 未達標：70以下
                格式：技術分：[數字]
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

    # 顯示分析結果與最終總結
    if st.session_state.get('done'):
        st.markdown(f'<div class="report-card">{st.session_state["report_text"]}</div>', unsafe_allow_html=True)
        
        if "🛑" not in st.session_state['report_text']:
            t_score = st.session_state['tech_score']
            # 計算公式
            data_contribution = data_points * w_data
            tech_contribution = t_score * w_tech
            final_total = data_contribution + tech_contribution
            
            st.divider()
            st.success("### 🏆 最終綜合成績判定")
            
            # 清楚顯示權重公式
            st.markdown(f"""
            #### 🧮 評分計算：
            - **數據分** ({w_data_pct}%): `{data_points}` × `{w_data}` = **{data_contribution:.1f}**
            - **技術分** ({w_tech_pct}%): `{t_score}` × `{w_tech}` = **{tech_contribution:.1f}**
            - **最終得分** : **{final_total:.1f} 分**
            """)
            
            if st.button("💾 儲存此診斷紀錄", use_container_width=True):
                new_res = {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"), "班級": sel_class, "座號": curr_stu['座號'],
                    "姓名": sel_name, "項目": sel_item, "數據分數": str(data_points),
                    "技術分數": str(t_score), "最終得分": str(round(final_total, 2)),
                    "AI診斷報告": st.session_state['report_text'].replace("\n", " ")
                }
                df_history = pd.concat([df_history, pd.DataFrame([new_res])], ignore_index=True).drop_duplicates(subset=["姓名", "項目"], keep="last")
                conn.update(worksheet="Analysis_Results", data=df_history)
                st.balloons()
                st.success("✅ 紀錄已成功存入雲端！")
        else:
            st.error("❌ 診斷未通過：影像與指標內容不符。")

# --- 5. 底部：個人歷程 ---
st.divider()
with st.expander("📚 查看該生歷史診斷紀錄"):
    p_history = df_history[df_history["姓名"] == sel_name]
    if not p_history.empty:
        st.dataframe(p_history[["時間", "項目", "最終得分", "技術分數", "數據分數"]], use_container_width=True)
