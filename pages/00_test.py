from pathlib import Path

import streamlit as st
from PIL import Image
from vertexai.preview.generative_models import Part

from mypylib.google_cloud_configuration import vertexai_configure
from mypylib.st_utils import (
    authenticate_and_configure_services,
    google_translate,
    load_vertex_model,
)

CURRENT_CWD: Path = Path(__file__).parent.parent

st.set_page_config(page_title="Streamlit test", layout="centered", page_icon="🧊")
# authenticate_and_configure_services()
vertexai_configure(st.secrets)
# import vertexai


st.title("Streamlit test")

image = Image.open(CURRENT_CWD / "resource" / "multimodal" / "timetable.png")

src = st.text_input("Text input", "default text")


placeholder = st.empty()

slider_status = st.sidebar.empty()
text = ""


def generate():
    global text
    text = ""
    model = load_vertex_model("gemini-pro-vision")
    responses = model.generate_content(
        [image, src],
        generation_config={"max_output_tokens": 1024, "temperature": 0.3, "top_p": 1},
        stream=True,
    )
    for response in responses:
        text += response.text
        placeholder.markdown(text + "▌")
    placeholder.markdown(text)


if st.button("提交", key="2"):
    generate()
