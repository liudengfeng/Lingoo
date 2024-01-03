import streamlit as st

# "第二页"

# st.markdown("""<a href="page1" target="_self">page 1</a>""", unsafe_allow_html=True)
import streamlit as st
from mypylib.st_helper import check_access, check_and_force_logout, configure_ais


st.set_page_config(
    page_title="听力练习",
    page_icon="🎧",
    layout="wide",
)

check_access(False)
configure_ais()

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(sidebar_status)

st.markdown("# 敬请期待......")
