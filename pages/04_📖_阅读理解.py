# import streamlit as st

# "第二页"

# st.markdown("""<a href="page1" target="_self">page 1</a>""", unsafe_allow_html=True)
import streamlit as st
import google.generativeai as palm

palm.configure(api_key=st.secrets["Google"]["PALM_API_KEY"])

st.set_page_config(
    page_title="阅读理解",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown("# 敬请期待......")
