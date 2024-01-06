import logging
import mimetypes
import time
import streamlit as st
from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS
from vertexai.preview.generative_models import GenerationConfig, Part
from mypylib.st_helper import (
    check_access,
    check_and_force_logout,
    configure_google_apis,
    load_vertex_model,
    setup_logger,
)


# region 页面设置

logger = logging.getLogger("streamlit")
setup_logger(logger)

st.set_page_config(
    page_title="聊天机器人",
    page_icon=":gemini:",
    layout="wide",
)
check_access(False)
configure_google_apis()

# endregion

# region 会话状态

AVATAR_NAMES = ["user", "model"]
AVATAR_EMOJIES = ["👨‍🎓", "🤖"]
AVATAR_MAPS = {name: emoji for name, emoji in zip(AVATAR_NAMES, AVATAR_EMOJIES)}

if "examples_pair" not in st.session_state:
    st.session_state["examples_pair"] = []

if "current_token_count" not in st.session_state:
    st.session_state["current_token_count"] = 0

if "total_token_count" not in st.session_state:
    st.session_state["total_token_count"] = st.session_state.dbi.get_token_count()

if st.session_state.get("clear_example"):
    st.session_state["user_text_area"] = ""
    st.session_state["ai_text_area"] = ""

if "multimodal_examples" not in st.session_state:
    st.session_state["multimodal_examples"] = []

# endregion

# region 辅助函数

# region 聊天机器人辅助函数


def initialize_chat_session():
    model = load_vertex_model("gemini-pro")
    history = []
    for user, ai in st.session_state["examples_pair"]:
        history.append({"role": "user", "parts": [user]})
        history.append({"role": "model", "parts": [ai]})
    st.session_state["chat_session"] = model.start_chat(history=history)
    st.session_state["chat_model"] = model


def add_chat_pairs():
    if st.session_state["user_text_area"] and st.session_state["ai_text_area"]:
        user = st.session_state["user_text_area"]
        ai = st.session_state["ai_text_area"]
        if st.session_state["examples_pair"]:
            prev = st.session_state["examples_pair"][-1]
            if prev[0] == user and prev[1] == ai:
                st.toast("示例对已存在.请点击🗑️清除后再添加。")
                st.stop()
        st.session_state["examples_pair"].append((user, ai))
        # st.write(st.session_state["examples_pair"])
        initialize_chat_session()
    else:
        st.toast("示例对不能为空。")


def delete_last_pair():
    if st.session_state["examples_pair"]:
        st.session_state["examples_pair"].pop()
        # st.write(st.session_state["examples_pair"])
        initialize_chat_session()


# endregion

# region 多模态辅助函数


def _process_media(uploaded_file):
    # 用文件扩展名称形成 MIME 类型
    mime_type = mimetypes.guess_type(uploaded_file.name)[0]
    p = Part.from_data(data=uploaded_file.getvalue(), mime_type=mime_type)  # type: ignore
    return {"mime_type": mime_type, "part": p}


def view_example(examples, container):
    for p in examples:
        mime_type = p["mime_type"]
        if mime_type.startswith("text"):
            container.markdown(p["part"].text)
        elif mime_type.startswith("image"):
            container.image(p["part"].inline_data.data, use_column_width=True)
        elif mime_type.startswith("video"):
            container.video(p["part"].inline_data.data)
    # 更新案例数量
    st.rerun()


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
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}"
    )


def clear_prompt(key):
    st.session_state[key] = ""


# endregion


# endregion

# region 主页

menu = st.sidebar.selectbox("菜单", options=["聊天机器", "工具能手", "示例教程"])
sidebar_status = st.sidebar.empty()
# TODO:暂时关闭
# check_and_force_logout(sidebar_status)

# region 聊天机器人

if menu == "聊天机器":
    # region 边栏

    st.sidebar.markdown(
        """:rainbow[运行设置]\n
:gemini: 模型：Gemini Pro            
    """
    )
    sidebar_cols = st.sidebar.columns(2)
    sidebar_cols[0].slider(
        "词元限制",
        key="max_output_tokens-chatbot",
        min_value=32,
        max_value=8192,
        value=2048,
        step=32,
        help="""✨ 词元限制决定了一条提示的最大文本输出量。词元约为 4 个字符。默认值为 2048。""",
    )
    # 生成参数
    sidebar_cols[1].slider(
        "温度",
        min_value=0.00,
        max_value=1.0,
        key="temperature-chatbot",
        value=0.9,
        step=0.1,
        help="✨ 温度可以控制词元选择的随机性。较低的温度适合希望获得真实或正确回复的提示，而较高的温度可能会引发更加多样化或意想不到的结果。如果温度为 0，系统始终会选择概率最高的词元。对于大多数应用场景，不妨先试着将温度设为 0.2。",
    )
    sidebar_cols[0].slider(
        "Top K",
        key="top_k-chatbot",
        min_value=1,
        max_value=40,
        value=40,
        step=1,
        help="""✨ Top-k 可更改模型选择输出词元的方式。
- 如果 Top-k 设为 1，表示所选词元是模型词汇表的所有词元中概率最高的词元（也称为贪心解码）。
- 如果 Top-k 设为 3，则表示系统将从 3 个概率最高的词元（通过温度确定）中选择下一个词元。
- Top-k 的默认值为 40。""",
    )
    sidebar_cols[1].slider(
        "Top P",
        key="top_p-chatbot",
        min_value=0.00,
        max_value=1.0,
        value=1.0,
        step=0.01,
        help="""✨ Top-p 可更改模型选择输出词元的方式。系统会按照概率从最高到最低的顺序选择词元，直到所选词元的概率总和等于 Top-p 的值。
- 例如，如果词元 A、B 和 C 的概率分别是 0.3、0.2 和 0.1，并且 Top-p 的值为 0.5，则模型将选择 A 或 B 作为下一个词元（通过温度确定）。
- Top-p 的默认值为 0.8。""",
    )

    st.sidebar.text_input(
        "添加停止序列",
        key="stop_sequences-chatbot",
        max_chars=64,
        help="✨ 停止序列是一连串字符（包括空格），如果模型中出现停止序列，则会停止生成回复。该序列不包含在回复中。您最多可以添加五个停止序列。",
    )

    user_example = st.sidebar.text_input(
        ":bust_in_silhouette: 用户示例",
        key="user_text_area",
        max_chars=1000,
    )
    ai_example = st.sidebar.text_input(
        ":gemini: 模型响应",
        key="ai_text_area",
        max_chars=1000,
    )

    sidebar_col1, sidebar_col2, sidebar_col3, sidebar_col4 = st.sidebar.columns(4)

    sidebar_col1.button(
        ":heavy_plus_sign:",
        on_click=add_chat_pairs,
        disabled=len(st.session_state["examples_pair"]) >= 8,
        help="""✨ 聊天提示的示例是输入输出对的列表，它们演示给定输入的示例性模型输出。控制在8对以内。使用示例来自定义模型如何响应某些问题。
|用户示例|AI示例|
|:-|:-|
|火星有多少颗卫星？|火星有两个卫星，火卫一和火卫二。|
    """,
    )
    sidebar_col2.button(
        ":heavy_minus_sign:",
        on_click=delete_last_pair,
        disabled=len(st.session_state["examples_pair"]) <= 0,
        help="✨ 删除最后一对示例",
    )
    sidebar_col3.button(
        ":wastebasket:",
        key="clear_example",
        help="✨ 清除当前示例对",
    )

    if sidebar_col4.button(
        ":arrows_counterclockwise:", key="reset_btn", help="✨ 重新设置上下文、示例，开始新的对话"
    ):
        st.session_state["examples_pair"] = []
        initialize_chat_session()

    with st.sidebar.expander("查看当前样例..."):
        if "chat_session" not in st.session_state:
            initialize_chat_session()
        num = len(st.session_state.examples_pair) * 2
        for his in st.session_state.chat_session.history[:num]:
            st.write(f"**{his.role}**：{his.parts[0].text}")

    help_info = "✨ 对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。"
    sidebar_status = st.sidebar.empty()
    # endregion

    # region 认证及强制退出

    check_and_force_logout(sidebar_status)

    # endregion

    # region 主页面
    st.subheader(":robot_face: Gemini 聊天机器人")
    if "chat_session" not in st.session_state:
        initialize_chat_session()

    # 显示会话历史记录
    start_idx = len(st.session_state.examples_pair) * 2
    for message in st.session_state.chat_session.history[start_idx:]:
        role = message.role
        with st.chat_message(role, avatar=AVATAR_MAPS[role]):
            st.markdown(message.parts[0].text)

    if prompt := st.chat_input("输入提示以便开始对话"):
        with st.chat_message("user", avatar=AVATAR_MAPS["user"]):
            st.markdown(prompt)

        config = {
            "temperature": st.session_state["temperature-chatbot"],
            "top_p": st.session_state["top_p-chatbot"],
            "top_k": st.session_state["top_k-chatbot"],
            "max_output_tokens": st.session_state["max_output_tokens-chatbot"],
        }
        try:
            response = st.session_state.chat_session.send_message(
                prompt,
                generation_config=config,
                safety_settings=DEFAULT_SAFETY_SETTINGS,
                stream=True,
            )
            with st.chat_message("assistant", avatar=AVATAR_MAPS["model"]):
                message_placeholder = st.empty()
                full_response = ""
                for chunk in response:
                    full_response += chunk.text
                    time.sleep(0.05)
                    # Add a blinking cursor to simulate typing
                    message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)
                # 令牌数
                st.session_state.current_token_count = (
                    st.session_state.chat_model.count_tokens(
                        prompt + full_response
                    ).total_tokens
                )
                st.session_state.total_token_count += (
                    st.session_state.current_token_count
                )
                # 添加记录到数据库
                st.session_state.dbi.add_token_record(
                    st.session_state.dbi.cache["phone_number"],
                    "gemini-pro-chatbot",
                    st.session_state.current_token_count,
                )
        # except ResponseBlockedError as e:
        #     # 处理被阻止的消息
        #     st.toast("抱歉，您尝试发送的消息包含潜在不安全的内容，已被阻止。")
        #     # 删除最后一对会话
        #     st.session_state.chat_session.rewind()
        except Exception as e:
            # 处理其他类型的异常
            st.write(e)

    msg = f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}"
    sidebar_status.markdown(msg, help=help_info)
    # st.write(st.session_state.chat_session.history)

    # endregion

# endregion

# region 工具能手

elif menu == "工具能手":
    # region 边栏
    sidebar_cols = st.sidebar.columns(2)
    st.sidebar.markdown(
        """:rainbow[运行设置]\n
:gemini: 模型：gemini-pro-vision            
    """
    )
    sidebar_cols[0].slider(
        "词元限制",
        key="max_output_tokens",
        min_value=16,
        max_value=2048,
        value=2048,
        step=16,
        help="""✨ 词元限制决定了一条提示的最大文本输出量。词元约为`4`个字符。默认值为`2048`""",
    )
    # 生成参数
    sidebar_cols[1].slider(
        "温度",
        min_value=0.00,
        max_value=1.0,
        key="temperature",
        value=0.0,
        step=0.1,
        help="✨ `temperature`（温度）可以控制词元选择的随机性。较低的温度适合希望获得真实或正确回复的提示，而较高的温度可能会引发更加多样化或意想不到的结果。如果温度为`0`，系统始终会选择概率最高的词元。对于大多数应用场景，不妨先试着将温度设为`0.2`。",
    )
    sidebar_cols[0].slider(
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
    sidebar_cols[1].slider(
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

    st.header(":rocket: :rainbow[通用多模态AI]", divider="rainbow", anchor=False)
    st.markdown("""您可以向`Gemini`模型发送多模态提示信息。支持的模态包括文字、图片和视频。""")

    items_emoji = ["1️⃣", "2️⃣"]
    items = ["背景指示", "运行模型"]
    tab_items = [f"{e} {i}" for e, i in zip(items_emoji, items)]
    tabs = st.tabs(tab_items)

    st.subheader(":clipboard: :blue[添加案例（可选）]", divider="rainbow", anchor=False)
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
    # 与上传文档控件高度相同
    ex_text = tab0_col2.text_area(
        "期望模型响应或指示词",
        placeholder="输入期望的响应",
        # height=60,
        key="ex_text_key",
        help="✨ 期望模型响应或指示词",
    )

    tab0_ex_btn_cols = st.columns([1, 1, 1, 1, 1, 5])

    add_media_btn = tab0_ex_btn_cols[0].button(
        ":film_projector:",
        help="✨ 添加图片或视频",
        key="add_media_btn",
    )
    add_text_btn = tab0_ex_btn_cols[1].button(
        ":memo:",
        help="✨ 添加指示词或期望模型的响应",
        key="add_text_btn",
    )
    del_last_btn = tab0_ex_btn_cols[2].button(
        ":rewind:", help="✨ 删除最后一条样本", key="del_last_example"
    )
    cls_ex_btn = tab0_ex_btn_cols[3].button(
        ":arrows_counterclockwise:", help="✨ 删除全部样本", key="clear_example"
    )

    st.subheader(
        f":clipboard: :blue[已添加的案例（{len(st.session_state.multimodal_examples)}）]",
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

    st.subheader(":bulb: :blue[提示词]", divider="rainbow", anchor=False)
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
        key="user_prompt_key",
        placeholder="请输入关于多媒体的提示词，例如：'描述这张风景图片'",
        max_chars=12288,
        height=300,
    )
    tab0_btn_cols = st.columns([1, 1, 8])
    # help="模型可以接受多个输入，以用作示例来了解您想要的输出。添加这些样本有助于模型识别模式，并将指定图片和响应之间的关系应用于新样本。这也称为少量样本学习。示例之间，添加'<>'符号用于分隔。"
    cls_btn = tab0_btn_cols[0].button(
        ":wastebasket:",
        help="✨ 清空提示词",
        key="clear_prompt",
        on_click=clear_prompt,
        args=("user_prompt_key",),
    )
    submitted = tab0_btn_cols[1].button("提交")

    response_container = st.container()

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

# endregion
