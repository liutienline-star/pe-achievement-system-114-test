import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import os
import time

# --- 1. 頁面設定與 API 初始化 ---
st.set_page_config(page_title="114學年度術科 AI 診斷系統", layout="wide")
st.title("🏆 體育術科專業 AI 診斷系統")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    MODEL_ID = "models/gemini-2.5-flash"
else:
    st.error("❌ 找不到 GOOGLE_API_KEY")
    st.stop()

# --- 2. GSheets 連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10) # 測試期間縮短緩存時間，讓修改立刻生效
def get_ai_criteria():
    try:
        # 讀取試算表
        df = conn.read(worksheet="AI_Criteria")
        # 自動修復：移除欄位名稱前後可能多出來的空格
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"讀取失敗，請確認分頁名稱是否為 'AI_Criteria'。錯誤訊息：{e}")
        return None

criteria_df = get_ai_criteria()

# --- 3. 核心邏輯 ---
if criteria_df is not None:
    try:
        # 定義您提供的精確欄位名稱
        COL_TEST = "測驗項目"
        COL_CONTEXT = "AI 指令脈絡 (AI_Context)"
        COL_INDICATORS = "具體指標 (Indicators)"
        COL_CUES = "專業指令與建議 (Cues)"

        # 檢查這些欄位是否真的存在
        existing_cols = criteria_df.columns.tolist()
        for col in [COL_TEST, COL_CONTEXT, COL_INDICATORS, COL_CUES]:
            if col not in existing_cols:
                st.error(f"⚠️ 找不到欄位：『{col}』")
                st.write("目前 Sheet 偵測到的欄位有：", existing_cols)
                st.stop()

        # 顯示選擇器
        test_list = criteria_df[COL_TEST].tolist()
        selected_test = st.selectbox("🎯 請選擇要診斷的術科項目", test_list)
        
        # 抓取對應資料
        row = criteria_df[criteria_df[COL_TEST] == selected_test].iloc[0]
        ai_context = row[COL_CONTEXT]
        indicators = row[COL_INDICATORS]
        cues = row[COL_CUES]

        # 顯示目前診斷標準在側邊欄
        with st.sidebar:
            st.header("📚 診斷參考標準")
            st.subheader(selected_test)
            st.markdown(f"**觀察指標：**\n{indicators}")
            st.markdown(f"**教學處方：**\n{cues}")

        # --- 影片分析介面 ---
        st.divider()
        uploaded_v = st.file_uploader(f"📹 上傳【{selected_test}】測驗影片", type=["mp4", "mov"])
        
        if uploaded_v:
            col_v, col_r = st.columns([1, 1])
            with col_v:
                st.video(uploaded_v)
            
            if st.button(f"🚀 啟動 {selected_test} 專業分析"):
                with col_r:
                    try:
                        temp_path = "temp_v.mp4"
                        with open(temp_path, "wb") as f:
                            f.write(uploaded_v.read())
                        
                        with st.spinner("⏳ 正在傳送影片..."):
                            video_file = genai.upload_file(path=temp_path)
                            while video_file.state.name == "PROCESSING":
                                time.sleep(2)
                                video_file = genai.get_file(video_file.name)
                        
                        with st.spinner("📋 AI 正在產生報告..."):
                            model = genai.GenerativeModel(MODEL_ID)
                            prompt = f"{ai_context}\n\n指標：\n{indicators}\n\n建議：\n{cues}"
                            response = model.generate_content([video_file, prompt])
                            st.success("分析完成！")
                            st.markdown(response.text)
                            
                        genai.delete_file(video_file.name)
                        os.remove(temp_path)
                    except Exception as e:
                        st.error(f"發生分析錯誤：{e}")

    except Exception as e:
        st.error(f"程式運行出錯：{e}")
