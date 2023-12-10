# import streamlit as st

# "第二页"

# st.markdown("""<a href="page1" target="_self">page 1</a>""", unsafe_allow_html=True)
import streamlit as st

from mypylib.streamlit_helper import check_and_force_logout

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(st, sidebar_status)

st.set_page_config(
    page_title="阅读理解",
    page_icon="📖",
    layout="wide",
)

st.markdown("# 敬请期待......")
