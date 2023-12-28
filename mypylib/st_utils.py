import streamlit as st


def check_and_force_logout(status):
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
