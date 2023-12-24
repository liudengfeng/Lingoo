import streamlit as st

from mypylib.st_helper import check_and_force_logout


st.set_page_config(
    page_title="写作练习",
    page_icon="✍️",
    layout="wide",
)

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(st, sidebar_status)

st.markdown("# 敬请期待......")
