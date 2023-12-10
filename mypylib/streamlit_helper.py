# streamlit 页面中的重复代码简化为函数
from .db_interface import DbInterface
from .google_api import init_vertex


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
        if "inited_vertex" not in st.session_state:
            init_vertex(st.secrets)
            st.session_state["inited_vertex"] = True
    else:
        st.error("非云端环境，无法使用 Vertex AI")
        st.stop()
