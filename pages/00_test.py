import streamlit as st

from mypylib.google_cloud_configuration import vertexai_configure
from mypylib.st_utils import (
    google_translate,
    authenticate_and_configure_services,
    load_model,
    load_vertex_model,
)

st.set_page_config(page_title="Streamlit test", layout="centered", page_icon="🧊")
# authenticate_and_configure_services()
vertexai_configure(st.secrets)
# import vertexai


st.title("Streamlit test")

src = st.text_input("Text input", "default text")

if st.button("翻译", key="1"):
    response = google_translate(src, "zh-CN")
    st.text(response)


placeholder = st.empty()

slider_status = st.sidebar.empty()
text = ""


def generate():
    global text
    text = ""
    # model = load_model("gemini-pro")
    model = load_vertex_model("gemini-pro")
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
