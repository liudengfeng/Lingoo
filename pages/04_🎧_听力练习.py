import streamlit as st

from mypylib.st_utils import (
    check_and_force_logout,
    authenticate_and_configure_services,
)

from mypylib.constants import CEFR_LEVEL_MAPS, rearrange_theme_scene
from mypylib.google_vertex import generate_sub_scenes

# "第二页"


# region 页面设置

st.set_page_config(
    page_title="听力练习",
    page_icon="🎧",
    layout="wide",
)

authenticate_and_configure_services()
st.markdown("""<a href="用户中心" target="_self">转移到用户中心</a>""", unsafe_allow_html=True)

# 添加会话变量
if "sub_scenes" not in st.session_state:
    st.session_state["sub_scenes"] = []

# endregion

# region 辅助函数


def on_theme_change():
    st.session_state["sub_scenes"] = generate_sub_scenes(selected_theme, st)


# endregion

# region 边栏

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(sidebar_status)

# 添加 CEFR 分级选择框
selected_cefr_level = st.sidebar.selectbox("选择你的 CEFR 分级", CEFR_LEVEL_MAPS.keys())
# 根据选定的 CEFR 分级显示相应的场景主题
selected_theme = st.sidebar.selectbox(
    "选择场景主题", rearrange_theme_scene()[selected_cefr_level], on_change=on_theme_change
)
# 添加子场景选择框，可选列表为会话变量
selected_sub_scene = st.sidebar.selectbox(
    "选择你偏好的听力练习场景", st.session_state["sub_scenes"]
)
# 显示计费令牌数
if "inited_google_ai" in st.session_state:
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}"
    )


# endregion


# region 主页

# 添加一行按钮
buttons = st.columns(4)
listen_button = buttons[0].button(":ear: 收听", help="✨ 点击开始收听")
reset_button = buttons[1].button(":arrows_counterclockwise: 重置", help="✨ 点击重置听力练习")
show_button = buttons[2].button(":eyes: 显示", help="✨ 点击显示听力材料")
test_button = buttons[3].button(":memo: 测试", help="✨ 点击开始测试")

# endregion
