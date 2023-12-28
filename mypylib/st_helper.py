import google.generativeai as genai

from mypylib.google_cloud_configuration import gemini_configure

from .db_interface import DbInterface


def authenticate(st):
    if "user_info" not in st.session_state:
        st.session_state["user_info"] = {}

    if "dbi" not in st.session_state:
        st.session_state["dbi"] = DbInterface()

    if not st.session_state.dbi.is_service_active(st.session_state["user_info"]):
        st.error("非付费用户，无法使用此功能。")
        st.stop()

    if st.secrets["env"] in ["streamlit", "azure"]:
        if "inited_google_ai" not in st.session_state:
            gemini_configure(st.secrets)
            st.session_state["inited_google_ai"] = True

        # 配置 token 计数器
        if "current_token_count" not in st.session_state:
            st.session_state["current_token_count"] = 0

        if "total_token_count" not in st.session_state:
            st.session_state["total_token_count"] = 0
    else:
        st.error("非云端环境，无法使用 Google AI")
        st.stop()
