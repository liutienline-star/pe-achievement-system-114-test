import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import os
import time
from datetime import datetime

# ==========================================
# 1. 頁面設定與登入檢查
# ==========================================
st.set_page_config(page_title="114學年度體育成績管理系統", layout="wide", page_icon="🏆")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True

    st.title("🔒 體育成績管理系統 - 登入")
    col1, _ = st.columns([1, 2])
    with col1:
        u = st.text_input("👤 管理員帳號")
        p = st.text_input("🔑 密碼", type="password")
        if st.button("🚀 確認登入"):
            if u == "tienline" and p == "641101":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("🚫 帳號或密碼錯誤")
    return False

if not check_password():
    st.stop()

# ==========================================
# 2. API 與資料連線 (支援 JSON Service Account)
# ==========================================
# AI 設定
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("❌ 找不到 GOOGLE_API_KEY，請檢查 Secrets 設定。")

# GSheets 連線
@st.cache_data(ttl=0)
def load_gsheets_data():
    try:
        # 自動讀取 Secrets 中的 [connections.gsheets] 區塊
        conn = st.connection("gsheets", type=GSheetsConnection)
        s_df = conn.read(worksheet="Scores").astype(str)
        l_df = conn.read(worksheet="Student_List").astype(str)
        n_df = conn.read(worksheet="Norms_Settings").astype(str)
        return s_df, l_df, n_df, None
    except Exception as e:
        return None, None, None, str(e)

scores_df, student_list, norms_df, conn_error = load_gsheets_data()

if conn_error:
    st.error(f"❌ 試算表連線失敗：{conn_error}")
    st.stop()

# ==========================================
# 3. 主介面導覽
# ==========================================
st.title("🏆 114學年度體育成績管理系統")
mode = st.radio("🎯 功能切換", ["一般術科測驗", "📊 數據報表查詢", "🤖 跳繩 AI 實驗室"], horizontal=True)
st.divider()

# --- 模式 1：一般術科測驗 ---
if mode == "一般術科測驗":
    st.header("📝 術科測驗錄入")
    st.info("這裡可以放置您原本的成績輸入邏輯。資料已成功連線至 `Scores` 分頁。")

# --- 模式 2：數據報表查詢 ---
elif mode == "📊 數據報表查詢":
    st.header("📈 成績報表查詢")
    if scores_df is not None:
        st.write("### 最近 20 筆錄入紀錄")
        st.dataframe(scores_df.tail(20), use_container_width=True)

# --- 模式 3：🤖 跳繩 AI 實驗室 (核心修正版) ---
elif mode == "🤖 跳繩 AI 實驗室":
    st.header("🤖 跳繩動作 AI 診斷")
    st.write("上傳影片後，AI 會自動分析次數與動作品質。")

    uploaded_video = st.file_uploader("📹 上傳影片 (mp4, mov)", type=["mp4", "mov", "avi"])

    if uploaded_video:
        st.video(uploaded_video)
        if st.button("🔍 開始 AI 教練分析"):
            try:
                # 1. 儲存暫存檔
                temp_path = "temp_jump_rope.mp4"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_video.read())
                
                # 2. 上傳影片至 Google AI
                with st.spinner("⏳ 正在將影片上傳至 AI 伺服器..."):
                    video_file = genai.upload_file(path=temp_path)
                
                # 3. 關鍵修正：輪詢影片狀態直到 ACTIVE
                with st.spinner("⏳ AI 正在解析影片內容 (這可能需要 10-20 秒)..."):
                    while video_file.state.name == "PROCESSING":
                        time.sleep(2)
                        video_file = genai.get_file(video_file.name)
                    
                    if video_file.state.name == "FAILED":
                        st.error("❌ 影片處理失敗，請嘗試其他影片。")
                        st.stop()

                # 4. 生成分析報告
                with st.spinner("📋 教練正在撰寫評語..."):
                    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
                    prompt = """
                    你現在是一位專業的體育教練。請分析這段跳繩影片並回答：
                    1. 【計次結果】：請算出成功跳過的總次數。
                    2. 【優點】：指出動作標準的地方（例如手腕運用、節奏穩定度）。
                    3. 【建議】：針對落地重心、腳部緩衝或繩子軌跡給予改進建議。
                    請用繁體中文回覆。
                    """
                    response = model.generate_content([video_file, prompt])
                    
                    st.success("✅ 分析完成")
                    st.markdown("---")
                    st.markdown(response.text)
                
                # 5. 清理資源
                genai.delete_file(video_file.name)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
            except Exception as e:
                st.error(f"❌ 分析過程發生錯誤：{e}")

# 側邊欄
st.sidebar.caption(f"📅 系統運行中 | {datetime.now().strftime('%Y-%m-%d')}")
st.sidebar.info("已串接 Google Sheets 與 Gemini 1.5 Flash")
