import streamlit as st

from mypylib.st_helper import (
    check_and_force_logout,
    authenticate,
    rearrange_theme_scene,
)
from mypylib.constants import CEFR_LEVEL_MAPS

# "第二页"

# st.markdown("""<a href="page1" target="_self">page 1</a>""", unsafe_allow_html=True)

st.set_page_config(
    page_title="听力练习",
    page_icon="🎧",
    layout="wide",
)

# region 边栏

authenticate(st)
sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(st, sidebar_status)

# 添加 CEFR 分级选择框
selected_cefr_level = st.sidebar.selectbox("选择你的 CEFR 分级", CEFR_LEVEL_MAPS.keys())
# 根据选定的 CEFR 分级显示相应的场景主题
selected_theme = st.sidebar.selectbox(
    "选择场景主题", rearrange_theme_scene()[selected_cefr_level]
)


# endregion


# region 主页

# 添加一行按钮
buttons = st.beta_columns(4)
listen_button = buttons[0].button(":ear: 收听", help="点击开始收听")
reset_button = buttons[1].button(":arrows_counterclockwise: 重置", help="点击重置听力练习")
show_button = buttons[2].button(":eyes: 显示", help="点击显示听力材料")
test_button = buttons[3].button(":memo: 测试", help="点击开始测试")

# endregion
