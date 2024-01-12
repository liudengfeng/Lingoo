from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="帮助中心",
    page_icon="🛠️",
    layout="centered",
)

CURRENT_CWD: Path = Path(__file__).parent.parent
VIDEO_DIR = CURRENT_CWD / "resource/video_tip"

st.subheader("常见问题", divider="rainbow_dash", anchor="常见问题")

with st.expander(":bulb: 如何注册？", expanded=False):
    # vfp = VIDEO_DIR / "单词" / "基础词库整体加入个人词库.mp4"
    # st.video(str(vfp))
    pass

with st.expander(":bulb: 如何订阅？", expanded=False):
    # vfp = VIDEO_DIR / "单词" / "基础词库整体加入个人词库.mp4"
    # st.video(str(vfp))
    pass

with st.expander(":bulb: 如何登录？", expanded=False):
    fp = VIDEO_DIR / "如何登录.mp4"
    st.video(str(fp))

with st.expander(":bulb: 忘记密码怎么办？", expanded=False):
    # vfp = VIDEO_DIR / "单词" / "基础词库整体加入个人词库.mp4"
    # st.video(str(vfp))
    pass
st.subheader("使用指南")
with st.expander(":bulb: 如何把一个基础词库整体添加到个人词库？", expanded=False):
    pass
st.subheader("联系我们")
