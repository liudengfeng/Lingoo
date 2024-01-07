import logging
import mimetypes
import time
from pathlib import Path

import streamlit as st
from vertexai.preview.generative_models import GenerationConfig, Part

from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS
from mypylib.st_helper import (
    check_access,
    check_and_force_logout,
    configure_google_apis,
    format_token_count,
    load_vertex_model,
    setup_logger,
)

# region 页面设置

# 创建或获取logger对象
logger = logging.getLogger("streamlit")
setup_logger(logger)

st.set_page_config(
    page_title="多模态AI",
    page_icon=":rocket:",
    layout="wide",
)
check_access(False)
configure_google_apis()

tab_emoji = [":globe_with_meridians:", ":speech_balloon:", ":bulb:"]
tab_names = ["通用", "翻译", "解题"]
tab_flags = [f"{e} {n}" for e, n in zip(tab_emoji, tab_names)]
tabs = st.tabs(tab_flags)


if "multimodal_examples" not in st.session_state:
    st.session_state["multimodal_examples"] = []


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
    f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{format_token_count(st.session_state.total_token_count)}",
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
    p = Part.from_data(data=uploaded_file.getvalue(), mime_type=mime_type)  # type: ignore
    return {"mime_type": mime_type, "part": p}


def view_example(examples, container):
    # for p in st.session_state.multimodal_examples:
    for p in examples:
        mime_type = p["mime_type"]
        if mime_type.startswith("text"):
            container.markdown(p["part"].text)
        elif mime_type.startswith("image"):
            container.image(p["part"].inline_data.data, use_column_width=True)
        elif mime_type.startswith("video"):
            container.video(p["part"].inline_data.data)


def generate_content_from_files_and_prompt(contents, response_container):
    model = load_vertex_model("gemini-pro-vision")
    generation_config = GenerationConfig(
        temperature=st.session_state["temperature"],
        top_p=st.session_state["top_p"],
        top_k=st.session_state["top_k"],
        max_output_tokens=st.session_state["max_output_tokens"],
    )
    responses = model.generate_content(
        [p["part"] for p in contents],
        generation_config=generation_config,
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        stream=True,
    )

    col1, col2 = response_container.columns(2)
    view_example(contents, col1)

    full_response = ""
    message_placeholder = col2.empty()
    for chunk in responses:  # type: ignore
        full_response += chunk.text
        time.sleep(0.05)
        # Add a blinking cursor to simulate typing
        message_placeholder.markdown(full_response + "▌")

    message_placeholder.markdown(full_response)
    # 令牌数
    st.session_state.current_token_count = model.count_tokens(
        [p["part"] for p in contents] + [Part.from_text(full_response)]
    ).total_tokens
    # 添加记录到数据库
    st.session_state.dbi.add_token_record(
        st.session_state.dbi.cache["phone_number"],
        "gemini-pro-vision",
        st.session_state.current_token_count,
    )
    st.session_state.total_token_count += st.session_state.current_token_count
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{format_token_count(st.session_state.total_token_count)}"
    )


def clear_prompt():
    st.session_state["user_prompt_key"] = ""


# endregion

# region 通用 AI

with tabs[0]:
    st.header(":rocket: :rainbow[通用多模态AI]", divider="rainbow", anchor=False)
    st.markdown("""您可以向`Gemini`模型发送多模态提示信息。支持的模态包括文字、图片和视频。""")

    st.subheader(":clipboard: :rainbow[添加案例（可选）]", divider="rainbow", anchor=False)
    st.markdown(
        "输入案例可丰富模型响应内容。`Gemini`模型可以接受多个输入，以用作示例来了解您想要的输出。添加这些样本有助于模型识别模式，并将指定图片和响应之间的关系应用于新样本。这也称为少量样本学习。"
    )

    tab0_col1, tab0_col2 = st.columns([1, 1])
    ex_media_file = tab0_col1.file_uploader(
        "插入多媒体文件【点击`Browse files`按钮，从本地上传文件】",
        accept_multiple_files=False,
        key="ex_media_file_key",
        type=["png", "jpg", "mkv", "mov", "mp4", "webm"],
        help="""
支持的格式
- 图片：PNG、JPG
- 视频：
    - 您可以上传视频，支持以下格式：MKV、MOV、MP4、WEBM（最大 7MB）
    - 该模型将分析长达 2 分钟的视频。 请注意，它将处理从视频中获取的一组不连续的图像帧。
    """,
    )

    ex_text = tab0_col2.text_area(
        "期望的响应",
        placeholder="输入期望的响应",
        key="ex_text_key",
        help="✨ 期望模型响应或标识",
    )

    tab0_ex_btn_cols = st.columns([1, 1, 1, 1, 6])

    add_media_btn = tab0_ex_btn_cols[0].button(
        ":film_projector:",
        help="✨ 添加图片或视频",
        key="add_media_btn",
    )
    add_text_btn = tab0_ex_btn_cols[1].button(
        ":memo:",
        help="✨ 添加文本",
        key="add_text_btn",
    )
    del_last_btn = tab0_ex_btn_cols[2].button(
        ":rewind:", help="✨ 删除最后一条样本", key="del_last_example"
    )
    cls_ex_btn = tab0_ex_btn_cols[3].button(
        ":arrows_counterclockwise:", help="✨ 删除全部样本", key="clear_example"
    )

    st.subheader(
        f":clipboard: :rainbow[已添加的案例（{len(st.session_state.multimodal_examples)}）]",
        divider="rainbow",
        anchor=False,
    )

    examples_container = st.container()

    if add_media_btn:
        if not ex_media_file:
            st.error("请添加多媒体文件")
            st.stop()
        p = _process_media(ex_media_file)
        st.session_state.multimodal_examples.append(p)
        view_example(st.session_state.multimodal_examples, examples_container)

    if add_text_btn:
        if not ex_text:
            st.error("请输入文本")
            st.stop()
        p = Part.from_text(ex_text)
        st.session_state.multimodal_examples.append({"mime_type": "text", "part": p})
        view_example(st.session_state.multimodal_examples, examples_container)

    if del_last_btn:
        if len(st.session_state["multimodal_examples"]) > 0:
            st.session_state["multimodal_examples"].pop()
            view_example(st.session_state.multimodal_examples, examples_container)

    if cls_ex_btn:
        st.session_state["multimodal_examples"] = []
        view_example(st.session_state.multimodal_examples, examples_container)

    st.subheader(":bulb: :rainbow[提示词]", divider="rainbow", anchor=False)
    uploaded_files = st.file_uploader(
        "插入多媒体文件【点击`Browse files`按钮，从本地上传文件】",
        accept_multiple_files=True,
        key="uploaded_files",
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
        # value=st.session_state["user_prompt"],
        key="user_prompt_key",
        placeholder="请输入关于多媒体的提示词，例如：'描述这张风景图片'",
        max_chars=12288,
        height=300,
    )
    tab0_btn_cols = st.columns([1, 1, 8])
    # help="模型可以接受多个输入，以用作示例来了解您想要的输出。添加这些样本有助于模型识别模式，并将指定图片和响应之间的关系应用于新样本。这也称为少量样本学习。示例之间，添加'<>'符号用于分隔。"
    cls_btn = tab0_btn_cols[0].button(
        ":wastebasket:", help="✨ 清空提示词", key="clear_prompt", on_click=clear_prompt
    )
    submitted = tab0_btn_cols[1].button("提交")

    response_container = st.container()

    # if cls_btn:
    #     st.session_state["user_prompt_key"] = ""
    #     st.rerun()

    if submitted:
        if uploaded_files is None or len(uploaded_files) == 0:  # type: ignore
            st.warning("您是否忘记了上传图片或视频？")
        if not prompt:
            st.error("请添加提示词")
            st.stop()
        contents = st.session_state.multimodal_examples.copy()
        if uploaded_files is not None:
            for m in uploaded_files:
                contents.append(_process_media(m))

        contents.append({"mime_type": "text", "part": Part.from_text(prompt)})
        generate_content_from_files_and_prompt(contents, response_container)

    # endregion

    # region 翻译AI

    with tabs[1]:
        pass

    # endregion

    # region 解题AI

    with tabs[2]:
        pass

# endregion
