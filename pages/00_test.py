import streamlit as st

from mypylib.google_apis import google_translate
from mypylib.google_cloud_configuration import get_translation_client

st.set_page_config(page_title="Streamlit test", layout="centered", page_icon="🧊")


# import vertexai

# vertexai.init(project="gllm-409401", location="asia-northeast1")


st.title("Streamlit test")

src = st.text_input("Text input", "default text")

if st.button("翻译", key="1"):
    response = google_translate(src, get_translation_client(st.secrets), "zh-CN")
    st.text(response)

import google.generativeai as genai

# from vertexai.preview.generative_models import GenerativeModel

genai.configure(api_key=st.secrets["Google"]["GEMINI_KEY"])

placeholder = st.empty()

slider_status = st.sidebar.empty()
text = ""


def generate():
    global text
    text = ""
    model = genai.GenerativeModel("gemini-pro")
    responses = model.generate_content(
        src,
        generation_config={"max_output_tokens": 1024, "temperature": 0.3, "top_p": 1},
        stream=True,
    )
    for response in responses:
        text += response.text
        placeholder.markdown(text + "▌")
    placeholder.markdown(text)


if st.button("提交", key="2"):
    generate()
