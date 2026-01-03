import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import re

# 頁面設定
st.set_page_config(page_title="114學年度體育成績管理系統", layout="wide")

# --- 0. 登入權限管理 (核心功能：完全保留) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True
    st.title("🔒 體育成績管理系統 - 登入")
    col1, _ = st.columns([1, 2])
    with col1:
        u = st.text_input("👤 管理員帳號", value="")
        p = st.text_input("🔑 密碼", type="password")
        if st.button("🚀 確認登入"):
            if u == "tienline" and p == "641101":
                st.session_state["password_correct"] = True
                st.rerun()
            else: st.error("🚫 帳號或密碼錯誤")
    return False

if not check_password(): st.stop()

# --- 1. 資料連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    scores_df = conn.read(worksheet="Scores", ttl="0s").astype(str)
    student_list = conn.read(worksheet="Student_List", ttl="0s").astype(str)
    norms_settings_df = conn.read(worksheet="Norms_Settings", ttl="0s").astype(str)
except Exception as e:
    st.error(f"讀取資料表失敗，請確保分頁名稱為 Scores, Student_List, Norms_Settings。錯誤: {e}")
    st.stop()

# --- 2. 輔助函式 ---
def clean_numeric_string(val):
    if pd.isna(val) or val == 'nan' or val == "": return ""
    s = str(val).strip()
    return str(int(float(s))) if re.match(r'^\d+\.0$', s) else s

def parse_time_to_seconds(time_str):
    try:
        s_val = str(time_str).strip()
        if ":" in s_val:
            main = s_val.split('.')[0]
            parts = main.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        return float(s_val)
    except: return 0

# --- 3. 萬用判定引擎 ---
def universal_judge(category, item, gender, age, value, norms_df):
    try:
        mask = (norms_df['測驗類別'] == category) & \
               (norms_df['項目名稱'] == item) & \
               (norms_df['性別'] == gender)
        filtered = norms_df[mask].copy()
        if filtered.empty: return "查無常模"

        age_int = int(float(age)) if age else 0
        age_mask = (filtered['年齡'].astype(float).astype(int) == age_int) | (filtered['年齡'].astype(float).astype(int) == 0)
        filtered = filtered[age_mask]
        if filtered.empty: return "待加強"

        v = parse_time_to_seconds(value)
        comp_method = filtered['比較方式'].iloc[0]

        if comp_method == ">=":
            sorted_norms = filtered.sort_values(by='門檻值', key=lambda x: x.astype(float), ascending=False)
            for _, rule in sorted_norms.iterrows():
                if v >= float(rule['門檻值']): return rule['判定結果']
        else:
            sorted_norms = filtered.sort_values(by='門檻值', key=lambda x: x.astype(float), ascending=True)
            for _, rule in sorted_norms.iterrows():
                if v <= float(rule['門檻值']): return rule['判定結果']
    except: pass
    return "待加強"

def judge_medal(item, gender, age, value):
    return universal_judge("體適能", item, gender, age, value, norms_settings_df)

def judge_subject_score(item, gender, value):
    return universal_judge("一般術科", item, gender, 0, value, norms_settings_df)

# --- 4. 側邊欄與資料清洗 ---
scores_df = scores_df.map(clean_numeric_string)
student_list = student_list.map(clean_numeric_string)

if not student_list.empty:
    cl_list = student_list['班級'].unique()
    sel_class = st.sidebar.selectbox("🏫 選擇班級", cl_list)
    stu_df = student_list[student_list['班級'] == sel_class]
    no_list = stu_df['座號'].sort_values(key=lambda x: pd.to_numeric(x, errors='coerce')).unique()
    sel_no = st.sidebar.selectbox("🔢 選擇學生座號", no_list)
    stu = stu_df[stu_df['座號'] == sel_no].iloc[0]
    st.sidebar.info(f"📌 {stu['姓名']} | {stu['性別']} | {stu['年齡']}歲")
else: st.stop()

# --- 5. 主介面 ---
st.title("🏆 114學年度體育成績管理系統")
mode = st.radio("🎯 功能切換", ["一般術科測驗", "114年體適能", "📊 數據報表查詢"], horizontal=True)

# [A. 一般術科測驗]
if mode == "一般術科測驗":
    col1, col2 = st.columns(2)
    with col1:
        test_cat = st.selectbox("🗂️ 類別", ["一般術科", "球類", "田徑", "其他"])
        subject_items = norms_settings_df[norms_settings_df['測驗類別'] != "體適能"]['項目名稱'].unique()
        test_item = st.selectbox("📝 項目", list(subject_items) + ["其他"])
        if test_item == "其他": test_item = st.text_input("✍️ 輸入項目名稱")
    with col2:
        fmt = st.selectbox("📏 格式", ["分數/個數 (純數字)", "秒數 (00.00)"])
        auto_j = st.checkbox("🤖 自動換算分數", value=True)
        manual_m = st.selectbox("🏅 等第", ["優", "甲", "乙", "丙", "丁", "尚未判定"])

    if "秒數" in fmt:
        c1, c2 = st.columns(2)
        final_score = f"{c1.number_input('秒', 0, 99, 13)}.{c2.number_input('毫秒', 0, 99, 0):02d}"
    else: 
        final_score = clean_numeric_string(st.text_input("📊 輸入數值", "0"))

    final_medal = judge_subject_score(test_item, stu['性別'], final_score) if auto_j else manual_m
    note = st.text_input("💬 備註", "")

    # 🕒 即時訊息方塊 (補回原本功能)
    st.write("🕒 **該項目近期測驗紀錄：**")
    recent = scores_df[(scores_df['姓名'] == stu['姓名']) & (scores_df['項目'] == test_item)]
    if not recent.empty:
        st.dataframe(recent[['紀錄時間', '成績', '等第/獎牌']].tail(3), use_container_width=True)
    else: 
        st.info("💡 此學生目前尚無該項目的歷史紀錄。")

# [B. 114年體適能]
elif mode == "114年體適能":
    test_cat = "體適能"
    status = st.selectbox("🩺 學生狀態", ["一般生", "身障/重大傷病 (比照銅牌)", "身體羸弱 (比照待加強)"])
    fitness_items = norms_settings_df[norms_settings_df['測驗類別'] == "體適能"]['項目名稱'].unique()
    test_item = st.selectbox("🏃 檢測項目", list(fitness_items))
    if status == "一般生":
        if "跑" in test_item or ":" in str(test_item):
            c1, c2 = st.columns(2)
            final_score, fmt = f"{c1.number_input('分', 0, 20, 8):02d}:{c2.number_input('秒', 0, 59, 0):02d}.0", "秒數 (00:00.0)"
        else:
            val = st.number_input("🔢 數據", 0.0, 500.0, 0.0)
            final_score, fmt = clean_numeric_string(val), "次數/公分"
        final_medal = judge_medal(test_item, stu['性別'], stu['年齡'], final_score)
        note = ""
    else:
        final_score, fmt = "N/A", "特殊判定"
        final_medal, note = ("銅牌" if "身障" in status else "待加強"), status

# [C. 數據報表查詢 (完整保留篩選與管理工具)]
elif mode == "📊 數據報表查詢":
    tab1, tab2, tab3 = st.tabs(["👤 個人成績單", "👥 班級總覽", "⚙️ 系統管理"])
    with tab1:
        p_data = scores_df[scores_df['姓名'] == stu['姓名']].copy()
        if not p_data.empty:
            c1, c2 = st.columns(2)
            with c1: p_cat = st.selectbox("🗂️ 篩選類別", ["顯示全部"] + list(p_data['測驗類別'].unique()), key="p1")
            with c2: p_it = st.selectbox("🎯 篩選項目", ["顯示全部"] + list(p_data['項目'].unique()), key="p2")
            if p_cat != "顯示全部": p_data = p_data[p_data['測驗類別'] == p_cat]
            if p_it != "顯示全部": p_data = p_data[p_data['項目'] == p_it]
            st.dataframe(p_data, use_container_width=True)
        else: st.info("尚無個人紀錄")
    with tab2:
        cl_data = scores_df[scores_df['班級'] == sel_class].copy()
        if not cl_data.empty:
            c1, c2 = st.columns(2)
            with c1: cl_cat = st.selectbox("🗂️ 篩選類別", ["顯示全部"] + list(cl_data['測驗類別'].unique()), key="c1")
            with c2: cl_it = st.selectbox("🎯 篩選項目", ["顯示全部"] + list(cl_data['項目'].unique()), key="c2")
            if cl_cat != "顯示全部": cl_data = cl_data[cl_data['測驗類別'] == cl_cat]
            if cl_it != "顯示全部": cl_data = cl_data[cl_data['項目'] == cl_it]
            st.dataframe(cl_data.sort_values(by='座號'), use_container_width=True)
            csv = cl_data.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載此報表 (CSV)", csv, f"{sel_class}_report.csv", "text/csv")
        else: st.info("該班尚無紀錄")
    with tab3:
        st.subheader("📝 常模即時編輯")
        edited_norms = st.data_editor(norms_settings_df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 儲存並同步更新常模"):
            conn.update(worksheet="Norms_Settings", data=edited_norms)
            st.success("常模已更新！"); st.rerun()
        
        st.divider()
        st.subheader("🛠️ 全校重新判定工具")
        if st.button("🚀 依照新常模重算全校分數"):
            with st.spinner("計算中..."):
                stu_info = student_list.set_index('姓名')[['性別', '年齡']].to_dict('index')
                for idx, row in scores_df.iterrows():
                    if row['姓名'] in stu_info:
                        s = stu_info[row['姓名']]
                        if row['測驗類別'] == "體適能":
                            scores_df.at[idx, '等第/獎牌'] = judge_medal(row['項目'], s['性別'], s['年齡'], row['成績'])
                        else:
                            scores_df.at[idx, '等第/獎牌'] = judge_subject_score(row['項目'], s['性別'], row['成績'])
                conn.update(worksheet="Scores", data=scores_df.map(clean_numeric_string))
                st.success("全校成績重算完成！"); st.rerun()

# --- 6. 存檔邏輯 (核心功能：及時覆蓋修正保留) ---
if mode in ["一般術科測驗", "114年體適能"]:
    st.divider()
    existing_mask = (scores_df['姓名'] == stu['姓名']) & (scores_df['項目'] == test_item)
    if existing_mask.any():
        old = scores_df[existing_mask].iloc[-1]
        st.warning(f"🕒 偵測到歷史紀錄：成績 {old['成績']} ({old['等第/獎牌']})")

    if st.button("💾 點擊確認：存入試算表"):
        new_row = {
            "紀錄時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "班級": sel_class, "座號": stu['座號'], "姓名": stu['姓名'],
            "測驗類別": test_cat, "項目": test_item, "成績": final_score,
            "顯示格式": fmt, "等第/獎牌": final_medal, "備註": note
        }
        if existing_mask.any():
            for k, v in new_row.items(): scores_df.loc[existing_mask, k] = str(v)
            final_df = scores_df
        else:
            final_df = pd.concat([scores_df, pd.DataFrame([new_row])], ignore_index=True)
        
        conn.update(worksheet="Scores", data=final_df.map(clean_numeric_string))
        st.balloons(); st.success("✅ 成績紀錄已成功同步！"); st.rerun()

if st.sidebar.button("🚪 登出系統"):
    st.session_state["password_correct"] = False
    st.rerun()
