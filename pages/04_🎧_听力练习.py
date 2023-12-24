import streamlit as st
from mypylib.google_api import generate_dialogue
from mypylib.st_helper import check_and_force_logout

# "第二页"

# st.markdown("""<a href="page1" target="_self">page 1</a>""", unsafe_allow_html=True)

st.set_page_config(
    page_title="听力练习",
    page_icon="🎧",
    layout="wide",
)

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(st, sidebar_status)

st.markdown("# 敬请期待......")
