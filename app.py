import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import os, time, re

# --- 1. 系統介面與風格設定 ---
st.set_page_config(page_title="AI 體育智慧診斷平台 v2.0", layout="wide", page_icon="🏅")

# 自定義美化 CSS
st.markdown("""
    <style>
    .main { background-color: #f9fbfd; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #e1e4e8; }
    .report-card { background-color: #ffffff; padding: 25px; border-radius: 15px; border-left: 6px solid #007bff; box-shadow: 0 4px 6px rgba(0,0,0,0.05); line-height: 1.6; }
    .formula-box { background-color: #eef6ff; padding: 15px; border-radius: 10px; border: 1px dashed #007bff; }
    </style>
    """, unsafe_allow_html=True)

# API KEY 驗證
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "gemini-2.0-flash" 
else:
    st.error("❌ 找不到 API_KEY，請檢查 Streamlit Secrets。"); st.stop()

# --- 2. 核心資料工具與讀取 (格式優化) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def clean_format(val):
    """徹底處理 .0 問題，同時保留非數字字串"""
    if pd.isna(val) or val == 'nan' or val == "": return ""
    s = str(val).strip()
    # 如果是數字結尾為 .0，則去除
    if s.endswith('.0'): s = s[:-2]
    return s

@st.cache_data(ttl=300)
def load_all_data():
    try:
        df_stu = conn.read(worksheet="Student_List").map(clean_format)
        df_cri = conn.read(worksheet="AI_Criteria").map(clean_format)
        df_sco = conn.read(worksheet="Scores").map(clean_format)
        try: 
            df_his = conn.read(worksheet="Analysis_Results").map(clean_format)
        except: 
            df_his = pd.DataFrame(columns=["時間", "班級", "座號", "姓名", "項目", "數據分數", "技術分數", "最終得分", "AI診斷報告"])
        return df_stu, df_cri, df_sco, df_his
    except Exception as e:
        st.error(f"📡 資料連結失敗，請檢查分頁名稱：{e}"); st.stop()

df_students, df_criteria, df_scores, df_history = load_all_data()

# --- 3. 側邊欄：導航與功能控制 ---
with st.sidebar:
    st.title("📂 學生檔案箱")
    
    # 班級選擇 (確保無 .0)
    all_classes = sorted(df_students["班級"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
    sel_class = st.selectbox("🏫 選擇班級", all_classes)
    
    # 學生選擇 (確保無 .0 且排序正確)
    stu_df = df_students[df_students["班級"] == sel_class].copy()
    stu_df["座號_int"] = pd.to_numeric(stu_df["座號"], errors="coerce").fillna(0).astype(int)
    stu_df = stu_df.sort_values("座號_int")
    
    stu_options = [f"【座號 {row['座號']}】{row['姓名']}" for _, row in stu_df.iterrows()]
    sel_option = st.selectbox("👤 選擇學生", stu_options)
    
    sel_name = re.search(r"】(.*)", sel_option).group(1)
    curr_stu = stu_df[stu_df["姓名"] == sel_name].iloc[0]
    
    st.divider()
    st.markdown(f"**當前診斷對象**：\n### {sel_name} ({curr_stu['性別']})")
    
    # 老師覆核開關
    manual_mode = st.checkbox("🛠️ 開啟老師手動覆核模式", help="當 AI 誤判或影片品質不佳時，可手動修正報告與分數。")
    
    if st.button("🔄 同步雲端最新數據"):
        st.cache_data.clear(); st.rerun()

# --- 4. 主介面：診斷儀表板 ---
st.title("🏆 AI 體育技術精準診斷系統")

# 第一區：設定與自動檢索
col_set, col_data = st.columns([1, 1.2])

with col_set:
    st.subheader("🎯 1. 診斷規準設定")
    sel_item = st.selectbox("請選擇測驗項目", df_criteria["測驗項目"].unique())
    c_row = df_criteria[df_criteria["測驗項目"] == sel_item].iloc[0]
    
    indicators = c_row.get("具體指標 (Indicators)", "未設定指標")
    context = c_row.get("AI 指令脈絡 (AI_Context)", "教學診斷與建議")
    
    # --- 權重解析修正段落 (請替換此部分) ---
    raw_logic = str(c_row.get("評分權重 (Scoring_Logic)", "70,30"))
    # 先抓取所有數字
    all_nums = [int(n) for n in re.findall(r"(\d+)", raw_logic)]
    
    # 【核心修正】：過濾掉小於或等於 5 的數字 (例如序號 1. 或 2.)
    # 體育權重通常不會設為 5% 以下，以此區隔「項目序號」與「實際權重」
    filtered_weights = [n for n in all_nums if n > 5]
    
    if len(filtered_weights) >= 2:
        w_data_pct = filtered_weights[0] # 抓到第一個大於 5 的數字 (如 70)
        w_tech_pct = filtered_weights[1] # 抓到第二個大於 5 的數字 (如 30)
    else:
        # 如果解析失敗（數字不足），則提供預設值 70, 30
        w_data_pct, w_tech_pct = 70, 30 
    
    # 轉換成小數點供後續計算使用
    w_data = w_data_pct / 100
    w_tech = w_tech_pct / 100
    # -----------------------------------
    
    with st.expander("🔍 檢視本項 AI 評分指標"):
        st.write(f"**技術規準：**\n{indicators}")
        st.caption(f"權重分配：數據 {w_data_pct}% / 技術 {w_tech_pct}%")

with col_data:
    st.subheader("📊 2. 原始成績自動對接")
    # 比對 Scores 分頁
    match = df_scores[(df_scores["姓名"] == sel_name) & (df_scores["項目"] == sel_item)]
    
    if not match.empty:
        last_rec = match.iloc[-1]
        raw_rec = last_rec.get("成績", "N/A") # 原始測驗錄入 (如: 12.5)
        score_val = pd.to_numeric(last_rec.get("等第/獎牌", 0), errors='coerce') # 轉化後的數據分
        
        st.info(f"✅ 已成功串聯 {sel_name} 的歷史成績")
        c_a, c_b = st.columns(2)
        c_a.metric("原始測驗紀錄", raw_rec)
        c_b.metric("數據轉化分數", f"{int(score_val)} 分")
    else:
        st.warning("⚠️ Scores 分頁中找不到對應成績")
        score_val = st.number_input("請手動輸入本次數據分數 (0-100)", 0, 100, 0)

st.divider()

# 第二區：影像與 AI 報告
v_col, r_col = st.columns([1, 1.3])

with v_col:
    st.subheader("📹 3. 技術動作影像")
    up_v = st.file_uploader(f"📎 上傳【{sel_item}】影片", type=["mp4", "mov"])
    if up_v:
        st.video(up_v)

with r_col:
    st.subheader("📝 4. AI 專業診斷分析")
    
    if st.button("🚀 啟動 AI 指標比對診斷", use_container_width=True) and up_v:
        with st.spinner("AI 考官正在嚴格對照指標進行分析..."):
            try:
                # 影片處理
                t_path = f"t_{int(time.time())}.mp4"
                with open(t_path, "wb") as f: f.write(up_v.read())
                v_f = genai.upload_file(path=t_path)
                while v_f.state.name == "PROCESSING": time.sleep(2); v_f = genai.get_file(v_f.name)
                
                # 核心 Prompt
                full_prompt = f"""
                你是體育鑑定專家。請針對【{sel_item}】進行診斷。
                技術指標："{indicators}"
                教學脈絡："{context}"

                ### 第一階段：視覺指標偵錯 (🛑)
                1. 比對影片是否包含技術指標："{indicators}"。
                2. 若影片內容完全不符或拍錯項目，請回報：🛑 項目偵錯錯誤。理由：[說明原因]。

                ### 第二階段：深度診斷 (即使表現不佳，只要項目正確，請務必循指標分析)
                請提供：[確認動作優點]、[關鍵改進點]、[練習處方與激勵]。

                ### 第三階段：技術評分 (嚴格對照指標達成率)
                - 完全達成：90-100 | 部分達成：80-89 | 基礎達成：75-79 | 未達標：70以下
                格式：技術分：[數字]
                """
                
                model = genai.GenerativeModel(MODEL_ID)
                response = model.generate_content([v_f, full_prompt])
                
                # 紀錄結果
                st.session_state['report'] = response.text
                s_match = re.search(r"技術分：(\d+)", response.text)
                st.session_state['t_score'] = int(s_match.group(1)) if s_match else 0
                st.session_state['is_done'] = True
                
                genai.delete_file(v_f.name); os.remove(t_path)
            except Exception as e: st.error(f"分析失敗：{e}")

    # 顯示結果
    if st.session_state.get('is_done') or manual_mode:
        report_text = st.session_state.get('report', "請啟動分析或手動輸入...")
        
        if manual_mode:
            st.warning("🛠️ 手動覆核模式已開啟，您可以直接編輯下方內容與分數。")
            report_text = st.text_area("編輯診斷報告內容", report_text, height=250)
            tech_score = st.number_input("調整技術分 (0-100)", 0, 100, st.session_state.get('t_score', 0))
        else:
            st.markdown(f'<div class="report-card">{report_text}</div>', unsafe_allow_html=True)
            tech_score = st.session_state.get('t_score', 0)

        # 最終判定邏輯
        if "🛑" not in report_text or manual_mode:
            # 計算貢獻分
            d_contrib = score_val * w_data
            t_contrib = tech_score * w_tech
            total_final = d_contrib + t_contrib
            
            st.divider()
            st.success("### 🏆 最終綜合判定成績")
            
            # 清楚顯示公式
            st.markdown(f"""
            <div class="formula-box">
                <b>🧮 綜合成績計算式：</b><br>
                數據分 ({w_data_pct}%): {score_val} × {w_data} = <b>{d_contrib:.1f}</b><br>
                技術分 ({w_tech_pct}%): {tech_score} × {w_tech} = <b>{t_contrib:.1f}</b><br>
                🎯 最終總得分：<span style="font-size: 24px; color: #d9534f;"><b>{total_final:.1f} 分</b></span>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("💾 確認無誤，儲存紀錄至雲端", use_container_width=True):
                new_row = {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "班級": sel_class, "座號": curr_stu['座號'], "姓名": sel_name,
                    "項目": sel_item, "數據分數": str(score_val),
                    "技術分數": str(tech_score), "最終得分": str(round(total_final, 2)),
                    "AI診斷報告": report_text.replace("\n", " ")
                }
                # 更新
                df_history = pd.concat([df_history, pd.DataFrame([new_row])], ignore_index=True).drop_duplicates(subset=["姓名", "項目"], keep="last")
                conn.update(worksheet="Analysis_Results", data=df_history)
                st.balloons(); st.success("✅ 紀錄已成功存入 Analysis_Results！")
        else:
            st.error("❌ 影像內容與技術指標不符。若 AI 判定有誤，請開啟左側『手動模式』覆核。")

# --- 5. 底部：歷史紀錄查詢 ---
st.divider()
with st.expander("📚 查看個人歷史診斷紀錄"):
    p_h = df_history[df_history["姓名"] == sel_name]
    if not p_h.empty:
        st.dataframe(p_h[["時間", "項目", "最終得分", "技術分數", "數據分數"]], use_container_width=True)
    else:
        st.write("目前尚無診斷紀錄。")
