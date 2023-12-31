import mimetypes
import time
from pathlib import Path

import streamlit as st
from vertexai.preview.generative_models import GenerationConfig, Part

from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS
from mypylib.st_utils import (
    authenticate_and_configure_services,
    check_and_force_logout,
    load_vertex_model,
)

# region 页面设置

st.set_page_config(
    page_title="多模态AI",
    page_icon=":rocket:",
    layout="wide",
)

tab_emoji = [":globe_with_meridians:", ":speech_balloon:", ":bulb:"]
tab_names = ["通用", "翻译", "解题"]
tab_flags = [f"{e} {n}" for e, n in zip(tab_emoji, tab_names)]
tabs = st.tabs(tab_flags)

authenticate_and_configure_services()

if "multimodal_examples_pair" not in st.session_state:
    st.session_state["multimodal_examples_pair"] = []

if "current_token_count" not in st.session_state:
    st.session_state["current_token_count"] = 0

if "total_token_count" not in st.session_state:
    st.session_state["total_token_count"] = 0

if "user_prompt" not in st.session_state:
    st.session_state["user_prompt"] = ""

if st.session_state.get("clear_prompt"):
    st.session_state["user_prompt"] = ""

# endregion

# region 边栏

st.sidebar.markdown(
    """:rainbow[运行设置]\n
:gemini: 模型：gemini-pro-vision            
"""
)
st.sidebar.slider(
    "词元限制",
    key="max_output_tokens",
    min_value=32,
    max_value=2048,
    value=2048,
    step=32,
    help="""✨ 词元限制决定了一条提示的最大文本输出量。词元约为`4`个字符。默认值为`2048`""",
)
# 生成参数
st.sidebar.slider(
    "温度",
    min_value=0.00,
    max_value=1.0,
    key="temperature",
    value=0.0,
    step=0.1,
    help="✨ `temperature`（温度）可以控制词元选择的随机性。较低的温度适合希望获得真实或正确回复的提示，而较高的温度可能会引发更加多样化或意想不到的结果。如果温度为`0`，系统始终会选择概率最高的词元。对于大多数应用场景，不妨先试着将温度设为`0.2`。",
)

st.sidebar.slider(
    "Top K",
    key="top_k",
    min_value=1,
    max_value=40,
    value=32,
    step=1,
    help="""✨ `Top-k`可更改模型选择输出词元的方式。
- 如果`Top-k`设为`1`，表示所选词元是模型词汇表的所有词元中概率最高的词元（也称为贪心解码）。
- 如果`Top-k`设为`3`，则表示系统将从`3`个概率最高的词元（通过温度确定）中选择下一个词元。
- 多模态`Top-k`的默认值为`32`。""",
)
st.sidebar.slider(
    "Top P",
    key="top_p",
    min_value=0.00,
    max_value=1.0,
    value=1.0,
    step=0.05,
    help="""✨ `Top-p`可更改模型选择输出词元的方式。系统会按照概率从最高到最低的顺序选择词元，直到所选词元的概率总和等于 Top-p 的值。
- 例如，如果词元`A`、`B` 和`C`的概率分别是`0.3`、`0.2`和`0.1`，并且`Top-p`的值为`0.5`，则模型将选择`A`或`B`作为下一个词元（通过温度确定）。
- 多模态`Top-p`的默认值为`1.0`。""",
)

st.sidebar.text_input(
    "添加停止序列",
    key="stop_sequences",
    max_chars=64,
    help="✨ 停止序列是一连串字符（包括空格），如果模型中出现停止序列，则会停止生成回复。该序列不包含在回复中。您最多可以添加五个停止序列。",
)
help_info = "✨ 对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。"
sidebar_status = st.sidebar.empty()
sidebar_status.markdown(
    f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}",
    help=help_info,
)

# endregion

# region 认证及强制退出

check_and_force_logout(sidebar_status)

# endregion

# region 辅助函数


def _process_media(uploaded_file):
    # 用文件扩展名称形成 MIME 类型
    mime_type = mimetypes.guess_type(uploaded_file.name)[0]
    return Part.from_data(data=uploaded_file.getvalue(), mime_type=mime_type)


def _process_image_and_prompt(uploaded_files, prompt):
    contents = []
    separator = "<>"
    if separator not in prompt:
        # 如果没有分隔符，代表没有示例
        for mf in uploaded_files:
            contents.append(_process_media(mf))
        contents.append(prompt)
        return contents
    ps = [p.strip() for p in prompt.split(separator)]
    msg = f"错误：多媒体文件的数量应等于提示的数量加1。请检查你的输入并重试。"
    if len(uploaded_files) != len(ps) + 1:
        st.error(msg)
        st.stop()
    # To read file as bytes:
    media_parts = [_process_media(m) for m in uploaded_files]
    for m, p in zip(media_parts[:-1], ps):
        contents.append(m)
        contents.append(p)
    contents.append(media_parts[-1])
    return contents


def generate_content_from_files_and_prompt(uploaded_files, prompt, response_container):
    try:
        contents = _process_image_and_prompt(uploaded_files, prompt)
    except Exception as e:
        st.error(f"处理多媒体文件时出错：{e}")
        return
    model = load_vertex_model("gemini-pro-vision")
    generation_config = GenerationConfig(
        temperature=st.session_state["temperature"],
        top_p=st.session_state["top_p"],
        top_k=st.session_state["top_k"],
        max_output_tokens=st.session_state["max_output_tokens"],
    )
    responses = model.generate_content(
        contents,
        generation_config=generation_config,
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        stream=True,
    )

    col1, col2 = response_container.columns(2)
    for m in uploaded_files:
        mime_type = mimetypes.guess_type(m.name)[0]
        if mime_type.startswith("image"):
            col1.image(m, use_column_width=True)
        elif mime_type.startswith("video"):
            col1.video(m)

    full_response = ""
    message_placeholder = col2.empty()
    for chunk in responses:
        full_response += chunk.text
        time.sleep(0.05)
        # Add a blinking cursor to simulate typing
        message_placeholder.markdown(full_response + "▌")

    message_placeholder.markdown(full_response)
    # 令牌数 TODO:需要考虑多媒体的令牌数
    st.session_state.current_token_count = model.count_tokens(
        prompt + full_response
    ).total_tokens
    st.session_state.total_token_count += st.session_state.current_token_count
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}"
    )


# endregion

# region 通用AI

with tabs[0]:
    st.header(":rocket: :rainbow[通用多模态AI]", divider="rainbow", anchor=False)
    st.markdown("""您可以向`Gemini`模型发送多模态提示信息。支持的模态包括文字、图片和视频。""")

    examples_container = st.container()

    uploaded_files = st.file_uploader(
        "插入多媒体文件【点击`Browse files`按钮，从本地上传文件】",
        accept_multiple_files=True,
        type=["png", "jpg", "mkv", "mov", "mp4", "webm"],
        help="""
    支持的格式
    - 图片：PNG、JPG
    - 视频：
        - 您可以上传视频，支持以下格式：MKV、MOV、MP4、WEBM（最大 7MB）
        - 该模型将分析长达 2 分钟的视频。 请注意，它将处理从视频中获取的一组不连续的图像帧。
    """,
    )

    prompt = st.text_area(
        "您的提示词",
        key="user_prompt_key",
        value=st.session_state.get("user_prompt", ""),
        placeholder="请输入关于多媒体的提示词，例如：'描述这张风景图片'",
        max_chars=12288,
        height=300,
    )
    cols = st.columns([1, 1, 1, 1, 1, 5])
    # help="模型可以接受多个输入，以用作示例来了解您想要的输出。添加这些样本有助于模型识别模式，并将指定图片和响应之间的关系应用于新样本。这也称为少量样本学习。示例之间，添加'<>'符号用于分隔。"
    add_btn = cols[0].button(
        ":film_projector:",
        help="✨ 模型可以接受多个输入，以用作示例来了解您想要的输出。添加这些样本有助于模型识别模式，并将指定图片和响应之间的关系应用于新样本。这也称为少量样本学习。",
    )
    del_btn = cols[1].button(":heavy_minus_sign:", help="✨ 删除提示词尾部的分隔符")
    cls_btn = cols[2].button(":wastebasket:", help="✨ 清空提示词", key="clear_prompt")
    submitted = cols[3].button("提交", help="✨ 如果含有示例响应，在多个响应之间，添加 '<>' 符号进行分隔。")

    response_container = st.container()

    if add_btn:
        video_file = st.file_uploader(
            "插入多媒体文件【点击`Browse file`按钮，从本地上传视频文件】",
            accept_multiple_files=False,
            type=["mkv", "mov", "mp4", "webm"],
            help="""
支持的格式
- 视频：
    - 您可以上传视频，支持以下格式：MKV、MOV、MP4、WEBM（最大 7MB）
    - 该模型将分析长达 2 分钟的视频。 请注意，它将处理从视频中获取的一组不连续的图像帧。
    """,
        )
        if video_file:
            mime_type = mimetypes.guess_type(video_file.name)[0]
            st.session_state.multimodal_examples_pair.append(_process_media(video_file))
            # examples_container.video(video_file, mime_type)
            # st.rerun()
            st.write("案例数量", len(st.session_state.multimodal_examples_pair))

    if del_btn:
        st.session_state["user_prompt"] = prompt.rstrip("<>\n")
        st.rerun()

    if submitted:
        if len(uploaded_files) == 0:
            st.error("请上传图片或视频")
            st.stop()
        if not prompt:
            st.error("请添加提示词")
            st.stop()
        generate_content_from_files_and_prompt(
            uploaded_files, prompt, response_container
        )

    # endregion

    # region 翻译AI

    with tabs[1]:
        pass

    # endregion

    # region 解题AI

    with tabs[2]:
        pass

# endregion
