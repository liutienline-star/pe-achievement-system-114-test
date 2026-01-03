import streamlit as st
import google.generativeai as genai

st.title("🔍 Gemini 模型權限診斷器")

# 從 Secrets 讀取金鑰
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    st.success("✅ 已讀取到 API 金鑰")
else:
    st.error("❌ Secrets 中找不到 GOOGLE_API_KEY")
    st.stop()

st.write("---")
st.subheader("📋 您目前金鑰可用的模型清單：")

try:
    available_models = []
    # 執行偵測
    for m in genai.list_models():
        # 只列出支援「內容生成」的模型
        if 'generateContent' in m.supported_generation_methods:
            available_models.append({
                "模型名稱 (ID)": m.name,
                "顯示名稱": m.display_name,
                "說明": m.description
            })
    
    if available_models:
        st.table(available_models)
        st.info(f"💡 您的下一步：請在程式碼中使用上方表格中『模型名稱』欄位的字串（例如：{available_models[0]['模型名稱 (ID)']}）")
    else:
        st.warning("⚠️ 找不到任何支援 generateContent 的模型。請檢查 Google AI Studio 的權限設定。")

except Exception as e:
    st.error(f"❌ 偵測時發生錯誤：{e}")
    st.info("這通常代表 API Key 無效，或該 Key 尚未啟用 Gemini API 權限。")
