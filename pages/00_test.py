import mimetypes
from pathlib import Path

import streamlit as st
from PIL import Image
from vertexai.preview.generative_models import Part
from vertexai.preview.generative_models import Image as GImage

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

st.header("Streamlit test", divider="rainbow")


def _process_media(uploaded_file):
    # 用文件扩展名称形成 MIME 类型
    return Image.from_bytes(uploaded_file.getvalue())
    # mime_type = mimetypes.guess_type(uploaded_file.name)[0]
    # return Part.from_data(data=uploaded_file.getvalue(), mime_type=mime_type)


uploaded_file = st.file_uploader(
    "插入多媒体文件【点击`Browse files`按钮，从本地上传文件】",
    accept_multiple_files=False,
    type=["png", "jpg"],
    help="""
支持的格式
- 图片：PNG、JPG
""",
)

src = st.text_input("Text input", "解析图片中的信息")


placeholder = st.empty()

slider_status = st.sidebar.empty()


def generate():
    text = ""
    model = load_vertex_model("gemini-pro-vision")
    responses = model.generate_content(
        [_process_media(uploaded_file), Part.from_text(src)],
        generation_config={"max_output_tokens": 1024, "temperature": 0.3, "top_p": 1},
        stream=True,
    )
    for response in responses:
        text += response.text
        placeholder.markdown(text + "▌")
    placeholder.markdown(text)


if st.button("提交", key="2"):
    generate()
