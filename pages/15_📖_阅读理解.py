import logging
import streamlit as st

from mypylib.st_helper import (
    check_access,
    check_and_force_logout,
    configure_google_apis,
    setup_logger,
)


# 创建或获取logger对象
logger = logging.getLogger("streamlit")
setup_logger(logger)

st.set_page_config(
    page_title="阅读理解",
    page_icon=":book:",
    layout="wide",
)

check_access(False)
configure_google_apis()

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(sidebar_status)
