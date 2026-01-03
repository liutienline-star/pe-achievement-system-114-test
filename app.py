import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import re

# 頁面設定
st.set_page_config(page_title="114學年度體育成績管理系統", layout="wide")

# --- AI 設定 ---
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("❌ 找不到 GOOGLE_API_KEY，請檢查 Secrets 設定。")

# --- 資料連線 (配合截圖名稱) ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 這裡的名稱與您的截圖分頁標籤完全一致
    scores_df = conn.read(worksheet="Scores", ttl="0s").astype(str)
    student_list = conn.read(worksheet="Student_List", ttl="0s").astype(str)
    norms_settings_df = conn.read(worksheet="Norms_Settings", ttl="0s").astype(str)
    
    # 偵測是否成功讀取 (排除 400 錯誤)
    if scores_df.empty:
        st.error("⚠️ 試算表讀取成功但內容為空，請確認分頁內容。")
except Exception as e:
    st.error(f"❌ 連線失敗：{e}")
    st.info("💡 建議檢查：1. 試算表是否已開啟『知道連結的任何人都能查看』。 2. Secrets 中的網址是否正確。")
    st.stop()

# --- 主介面 ---
st.title("🏆 體育成績管理系統 (AI 跳繩實驗版)")

# 模式切換
mode = st.radio("🎯 功能切換", ["一般術科測驗", "📊 數據報表查詢", "🤖 跳繩 AI 實驗室"], horizontal=True)

if mode == "🤖 跳繩 AI 實驗室":
    st.subheader("🧪 跳繩動作即時分析")
    
    uploaded_video = st.file_uploader("📹 上傳跳繩影片", type=["mp4", "mov", "avi"])

    if uploaded_video:
        st.video(uploaded_video)
        if st.button("🔍 開始 AI 分析"):
            try:
                with st.spinner("教練正在分析中，請稍候..."):
                    # 暫存影片
                    with open("temp_video.mp4", "wb") as f:
                        f.write(uploaded_video.read())
                    
                    # 上傳至 Google AI
                    video_file = genai.upload_file(path="temp_video.mp4")
                    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
                    
                    # 配合截圖欄位的專業指令
                    prompt = """
                    你現在是專業體育老師。請分析這段跳繩影片：
                    1. 計算總次數。
                    2. 優點：請針對手腕擺動與節奏進行分析。
                    3. 缺點：請針對落地重心與腳部緩衝進行分析。
                    4. 建議：給予具體的改進練習建議。
                    請用繁體中文回覆。
                    """
                    
                    response = model.generate_content([prompt, video_file])
                    
                    st.success("✅ 分析完成")
                    st.markdown("---")
                    st.markdown(response.text)
                    
            except Exception as e:
                st.error(f"分析過程發生錯誤：{e}")

# --- 其他原本的功能保留在此之後 ---
# (請將您原本的 A, B 功能代碼貼在下方)
