import streamlit as st

from mypylib.st_helper import check_access, configure_google_apis

# region 配置

st.set_page_config(
    page_title="练习",
    page_icon=":muscle:",
    layout="wide",
)

check_access(False)
configure_google_apis()

# endregion

menu_items = ["词汇练习", "口语练习", "听力练习", "阅读练习", "写作练习", "语法练习"]
