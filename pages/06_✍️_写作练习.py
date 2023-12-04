import streamlit as st
import google.generativeai as palm

palm.configure(api_key=st.secrets["Google"]["PALM_API_KEY"])

st.set_page_config(
    page_title="写作练习",
    page_icon="✍️",
    layout="wide",
)

st.markdown("# 敬请期待......")
