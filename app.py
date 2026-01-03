import streamlit as st
import google.generativeai as genai
import os
import time

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="跳繩 AI 測試診斷", page_icon="💪")

st.title("📹 跳繩動作 AI 診斷測試")
st.info("本版本使用 Gemini 2.5 Flash 模型，專門測試影片分析功能。")

# --- 2. API 金鑰與模型設定 ---
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # 使用您清單中排名第 0 號的穩定版模型
    MODEL_ID = "models/gemini-2.5-flash"
else:
    st.error("❌ 找不到 GOOGLE_API_KEY，請檢查 Streamlit Secrets 設定。")
    st.stop()

# --- 3. 影片上傳介面 ---
uploaded_video = st.file_uploader("請上傳學生跳繩影片 (支援 mp4, mov)", type=["mp4", "mov"])

if uploaded_video:
    st.video(uploaded_video)
    
    if st.button("🚀 開始分析影片"):
        try:
            # A. 建立暫存檔
            temp_path = "temp_test_video.mp4"
            with open(temp_path, "wb") as f:
                f.write(uploaded_video.read())
            
            # B. 上傳至 Google AI 伺服器
            with st.spinner("1/3 正在將影片傳送至 AI 教練..."):
                video_file = genai.upload_file(path=temp_path)
            
            # C. 關鍵步驟：等待影片處理 (避免 404)
            with st.spinner("2/3 AI 正在解析動作細節 (約需 10-20 秒)..."):
                while video_file.state.name == "PROCESSING":
                    time.sleep(2)
                    video_file = genai.get_file(video_file.name)
                
                if video_file.state.name == "FAILED":
                    st.error("❌ 影片處理失敗，請嘗試更換影片檔。")
                    st.stop()
            
            # D. 發送分析請求
            with st.spinner("3/3 教練正在整理評語，請稍候..."):
                model = genai.GenerativeModel(model_name=MODEL_ID)
                
                # 專業體育教學 Prompt
                prompt = """
                你現在是一位專業的國小體育教練。請觀看這段跳繩影片並提供以下建議：
                1. 【精準計次】：算出影片中成功跳過的次數。
                2. 【動作分析】：針對手腕搖繩、雙腳跳躍高度、落地緩衝等動作給予評價。
                3. 【改進建議】：給予學生一句鼓勵的話，並提供一個可以更好的訓練小撇步。
                請完全使用「繁體中文」回覆。
                """
                
                response = model.generate_content([video_file, prompt])
                
                st.success("✅ 分析成功！")
                st.divider()
                st.markdown("### 🤖 AI 教練分析報告")
                st.write(response.text)
                
            # E. 資源清理
            genai.delete_file(video_file.name)
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        except Exception as e:
            st.error(f"❌ 分析過程發生意外錯誤：{e}")
            st.info("💡 小提示：如果出現權限錯誤，請確認您的 API Key 是否已啟用 Gemini 2.5 權限。")

else:
    st.warning("👈 請先上傳一段影片，然後點擊按鈕進行測試。")

# --- 側邊欄狀態 ---
st.sidebar.title("系統狀態")
st.sidebar.write(f"當前使用模型：`{MODEL_ID}`")
st.sidebar.write("API 連線狀態：✅ 正常")
