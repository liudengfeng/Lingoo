import google.generativeai as genai

from mypylib.google_cloud_configuration import gemini_configure

from .db_interface import DbInterface


def check_and_force_logout(st, status):
    """
    检查并强制退出用户重复登录。

    Args:
        st (object): Streamlit 模块。
        status (object): Streamlit 状态元素，用于显示错误信息。

    Returns:
        None
    """
    if "user_info" in st.session_state and "session_id" in st.session_state.user_info:
        # 获取除最后一个登录事件外的所有未退出的登录事件
        active_sessions = st.session_state.dbi.get_active_sessions(
            st.session_state.user_info["user_id"]
        )
        for session in active_sessions:
            if session.session_id == st.session_state.user_info["session_id"]:
                # 如果 st.session_state 中的会话ID在需要强制退出的列表中，处理强制退出
                st.session_state.dbi.force_logout_session(
                    st.session_state.user_info["user_id"], session.session_id
                )
                st.session_state.clear()
                status.error("您的账号在其他设备上登录，您已被强制退出。")
                st.stop()


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
