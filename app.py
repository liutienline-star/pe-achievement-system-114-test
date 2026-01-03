import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import re
import os
from datetime import datetime

# ==========================================
# 1. 頁面基本設定與安全檢查
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
# 2. API 與資料庫連線設定
# ==========================================
# AI 金鑰設定
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("❌ 找不到 GOOGLE_API_KEY，請至 Streamlit Secrets 設定。")

# GSheets 連線
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    # 根據老師截圖的分頁名稱進行讀取
    scores_df = conn.read(worksheet="Scores", ttl="0s").astype(str)
    student_list = conn.read(worksheet="Student_List", ttl="0s").astype(str)
    norms_settings_df = conn.read(worksheet="Norms_Settings", ttl="0s").astype(str)
except Exception as e:
    st.error(f"❌ 試算表連線失敗：{e}")
    st.info("💡 請檢查 Secrets 網址是否正確，並確保試算表已開啟『知道連結的人員』檢視權限。")
    st.stop()

# ==========================================
# 3. 主選單介面
# ==========================================
st.title("🏆 114學年度體育成績管理系統")
mode = st.radio("🎯 功能切換", ["一般術科測驗", "📊 數據報表查詢", "🤖 跳繩 AI 實驗室"], horizontal=True)
st.divider()

# --- 模式 1：一般術科測驗 (老師可在此處貼入原本的錄入邏輯) ---
if mode == "一般術科測驗":
    st.header("📝 術科測驗錄入")
    st.info("請將您原本用於選擇班級、座號、錄入成績的程式碼邏輯貼於此處。")

# --- 模式 2：數據報表查詢 ---
elif mode == "📊 數據報表查詢":
    st.header("📈 成績報表查詢")
    st.write("目前 `Scores` 分頁中的最新紀錄：")
    if not scores_df.empty:
        st.dataframe(scores_df.tail(20), use_container_width=True)
    else:
        st.warning("目前暫無成績資料。")

# --- 模式 3：🤖 跳繩 AI 實驗室 ---
elif mode == "🤖 跳繩 AI 實驗室":
    st.header("🤖 跳繩動作 AI 診斷")
    st.write("上傳學生跳繩影片，AI 將自動計次並提供技術分析。")

    col_v, col_r = st.columns([1, 1])

    with col_v:
        uploaded_video = st.file_uploader("📹 上傳影片 (mp4, mov)", type=["mp4", "mov", "avi"])
        if uploaded_video:
            st.video(uploaded_video)

    if uploaded_video:
        with col_r:
            if st.button("🔍 開始教練分析"):
                try:
                    with st.spinner("教練正在仔細觀察學生的動作..."):
                        # 儲存暫存檔案
                        temp_path = "temp_jump_rope.mp4"
                        with open(temp_path, "wb") as f:
                            f.write(uploaded_video.read())
                        
                        # 上傳至 Google AI 伺服器
                        video_file = genai.upload_file(path=temp_path)
                        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
                        
                        # 專業分析指令
                        prompt = """
                        你現在是一位專業的體育教練。請分析這段跳繩影片並回答：
                        1. 【計次結果】：請算出成功跳過的總次數。
                        2. 【優點】：指出動作標準的地方(如手腕運用、節奏)。
                        3. 【缺點與建議】：指出不標準處(如重心落地過重、勾腿)並給予調整建議。
                        請用「繁體中文」回覆，語氣要給予學生鼓勵。
                        """
                        
                        response = model.generate_content([prompt, video_file])
                        
                        # 顯示分析結果
                        st.success("✅ 分析完成")
                        st.markdown("### 📋 AI 教練回報：")
                        st.markdown(response.text)
                        
                        # 結束後移除暫存檔
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                
                except Exception as e:
                    st.error(f"❌ AI 分析發生錯誤：{e}")

# 側邊欄資訊
st.sidebar.markdown("---")
st.sidebar.caption(f"📅 系統最後更新：{datetime.now().strftime('%Y-%m-%d')}")
st.sidebar.info("本系統已整合 Gemini 1.5 Flash 影像分析技術")
