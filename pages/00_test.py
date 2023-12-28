import streamlit as st

from mypylib.google_apis import google_translate
from mypylib.google_cloud_configuration import get_translation_client

st.set_page_config(page_title="Streamlit test", layout="centered", page_icon="🧊")

st.title("Streamlit test")

src = st.text_input("Text input", "default text")

if st.button("翻译", key="1"):
    response = google_translate(src, get_translation_client(st.secrets), "zh-CN")
    st.text(response)


from vertexai.preview.generative_models import GenerativeModel

model = GenerativeModel("gemini-pro")

responses = model.generate_content("The opposite of hot is", stream=True)

if st.button("翻译", key="2"):
    for response in responses:
        st.text(response.text)
