import streamlit as st

from mypylib.google_apis import google_translate
from mypylib.google_cloud_configuration import get_translation_client

st.set_page_config(page_title="Streamlit test", layout="centered", page_icon="🧊")


import vertexai

vertexai.init(project="gllm-409401", location="asia-northeast1")

st.title("Streamlit test")

src = st.text_input("Text input", "default text")

if st.button("翻译", key="1"):
    response = google_translate(src, get_translation_client(st.secrets), "zh-CN")
    st.text(response)


from vertexai.preview.generative_models import GenerativeModel

model = GenerativeModel("gemini-pro")

placeholder = st.empty()


def generate():
    model = GenerativeModel("gemini-pro")
    responses = model.generate_content(
        src,
        generation_config={"max_output_tokens": 2048, "temperature": 0.9, "top_p": 1},
        stream=True,
    )
    for response in responses:
        placeholder.markdown(response.text)


if st.button("提交", key="2"):
    generate()
