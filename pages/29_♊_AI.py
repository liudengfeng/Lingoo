import streamlit as st


menu = st.sidebar.selectbox("菜单", options=["聊天机器人", "处理反馈", "词典管理", "统计分析"])
sidebar_status = st.sidebar.empty()
# TODO:暂时关闭
# check_and_force_logout(sidebar_status)
