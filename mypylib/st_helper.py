import google.generativeai as genai

from .constants import THEME_SCENE
from .db_interface import DbInterface


def rearrange_theme_scene():
    level_to_theme = {}
    for theme, levels in THEME_SCENE.items():
        for level in levels:
            if level not in level_to_theme:
                level_to_theme[level] = [theme]
            else:
                level_to_theme[level].append(theme)
    return level_to_theme


def configure(st):
    GOOGLE_API_KEY = st.secrets["Google"]["GAI_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)


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
            configure(st)
            st.session_state["inited_google_ai"] = True
    else:
        st.error("非云端环境，无法使用 Google AI")
        st.stop()
