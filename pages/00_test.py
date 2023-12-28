import streamlit as st
from mypylib.google_cloud_configuration import get_translation_client
from mypylib.google_apis import google_translate

st.set_page_config(page_title="Streamlit test", layout="centered", page_icon="🧊")

st.title("Streamlit test")

src = st.text_input("Text input", "default text")

if st.button("翻译"):
    response = google_translate(src, get_translation_client(st.secrets), "zh-CN")
    st.text(response)
