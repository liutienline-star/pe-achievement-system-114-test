import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import os
import time

# --- 1. 頁面設定 ---
st.set_page_config(page_title="114學年度術科 AI 診斷系統", layout="wide")
st.title("🏆 體育術科專業 AI 診斷系統")
st.caption("連線狀態：已掛載 Google Sheets 動態指標資料庫")

# --- 2. API 與資料連線 ---
# AI 設定
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "models/gemini-2.5-flash"
else:
    st.error("❌ 找不到 GOOGLE_API_KEY")
    st.stop()

# GSheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)  # 每分鐘更新一次，方便老師修改 Sheet 後快速生效
def get_ai_criteria():
    try:
        df = conn.read(worksheet="AI_Criteria")
        return df
    except Exception as e:
        st.error(f"無法讀取 AI_Criteria 分頁：{e}")
        return None

criteria_df = get_ai_criteria()

# --- 3. 介面與邏輯 ---
if criteria_df is not None:
    # 讓老師選擇科目（名稱會跟著 Sheet 變動）
    test_list = criteria_df["測驗項目"].tolist()
    selected_test = st.selectbox("🎯 請選擇要診斷的術科項目", test_list)
    
    # 抓取該項目的詳細指標
    row = criteria_df[criteria_df["測驗項目"] == selected_test].iloc[0]
    ai_context = row["AI 指令脈絡"]
    indicators = row["具體指標"]
    cues = row["專業指令與建議"]

    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📹 上傳測驗影片")
        uploaded_v = st.file_uploader(f"請上傳【{selected_test}】影片", type=["mp4", "mov"])
        if uploaded_v:
            st.video(uploaded_v)

    with col2:
        st.subheader("🤖 AI 診斷報告")
        if uploaded_v and st.button(f"🔍 開始執行 {selected_test} 專業分析"):
            try:
                # A. 處理暫存與上傳
                temp_path = "temp_analysis.mp4"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_v.read())
                
                with st.spinner("⏳ 正在傳送影片至 AI 伺服器..."):
                    video_file = genai.upload_file(path=temp_path)
                
                # B. 等待處理
                with st.spinner("⏳ AI 正在比對指標庫進行診斷..."):
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2)
                        video_file = genai.get_file(video_file.name)
                
                # C. 生成動態 Prompt 並要求分析
                with st.spinner("📋 正在撰寫分析報告..."):
                    model = genai.GenerativeModel(model_name=MODEL_ID)
                    
                    # 這裡就是把您的 Sheet 內容組合起來
                    dynamic_prompt = f"""
                    {ai_context}
                    
                    請針對以下具體指標進行深度觀察與評分：
                    {indicators}
                    
                    分析完成後，請根據以下教學處方給予學生建議：
                    {cues}
                    
                    請完全使用「繁體中文」並以 Markdown 格式回覆。
                    """
                    
                    response = model.generate_content([video_file, dynamic_prompt])
                    st.success("分析完成！")
                    st.markdown(response.text)
                
                # D. 清理
                genai.delete_file(video_file.name)
                os.remove(temp_path)

            except Exception as e:
                st.error(f"分析過程發生錯誤：{e}")
else:
    st.warning("請確認 Google Sheets 中有名為 'AI_Criteria' 的分頁，且欄位名稱正確。")

# --- 側邊欄：顯示目前的參考指標 ---
if criteria_df is not None:
    st.sidebar.title("📚 當前診斷標準")
    st.sidebar.info(f"**項目：** {selected_test}")
    st.sidebar.write("**AI 視角：**")
    st.sidebar.caption(ai_context)
    st.sidebar.write("**觀察重點：**")
    st.sidebar.caption(indicators)
