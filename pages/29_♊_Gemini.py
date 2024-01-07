import logging
import mimetypes
import time
from pathlib import Path

import streamlit as st
from vertexai.preview.generative_models import GenerationConfig, Part

from mypylib.google_ai import generate_content_and_update_token
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

logger = logging.getLogger("streamlit")
setup_logger(logger)

CURRENT_CWD: Path = Path(__file__).parent.parent
IMAGE_DIR: Path = CURRENT_CWD / "resource/multimodal"

st.set_page_config(
    page_title="人工智能",
    page_icon=":gemini:",
    layout="wide",
)
check_access(False)
configure_google_apis()
help_info = "✨ 对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。"
# endregion

# region 会话状态

gemini_pro_vision_generation_config = {
    "max_output_tokens": 2048,
    "temperature": 0.4,
    "top_p": 1,
    "top_k": 32,
}

AVATAR_NAMES = ["user", "model"]
AVATAR_EMOJIES = ["👨‍🎓", "🤖"]
AVATAR_MAPS = {name: emoji for name, emoji in zip(AVATAR_NAMES, AVATAR_EMOJIES)}

if "examples_pair" not in st.session_state:
    st.session_state["examples_pair"] = []

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
    cols = container.columns(2)
    for i, p in enumerate(examples):
        mime_type = p["mime_type"]
        if mime_type.startswith("text"):
            cols[i % 2].markdown(p["part"].text)
        elif mime_type.startswith("image"):
            cols[i % 2].image(p["part"].inline_data.data, width=300)
        elif mime_type.startswith("video"):
            cols[i % 2].video(p["part"].inline_data.data)


def process_files_and_prompt(uploaded_files, prompt):
    contents = st.session_state.multimodal_examples.copy()
    if uploaded_files is not None:
        for m in uploaded_files:
            contents.append(_process_media(m))
    contents.append({"mime_type": "text", "part": Part.from_text(prompt)})
    return contents


def generate_content_from_files_and_prompt(contents, placeholder):
    model = load_vertex_model("gemini-pro-vision")
    generation_config = GenerationConfig(
        temperature=st.session_state["temperature"],
        top_p=st.session_state["top_p"],
        top_k=st.session_state["top_k"],
        max_output_tokens=st.session_state["max_output_tokens"],
    )
    generate_content_and_update_token(
        "多模态AI",
        model,
        [p["part"] for p in contents],
        generation_config,
        stream=True,
        placeholder=placeholder,
    )


def clear_prompt(key):
    st.session_state[key] = ""


# endregion


# endregion

# region 主页

menu = st.sidebar.selectbox("菜单", options=["聊天机器人", "多模态AI", "示例教程"])
sidebar_status = st.sidebar.empty()
check_and_force_logout(sidebar_status)

# region 聊天机器人

if menu == "聊天机器人":
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

    sidebar_status = st.sidebar.empty()
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{format_token_count(st.session_state.total_token_count)}",
        help=help_info,
    )
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
        config = GenerationConfig(**config)
        with st.chat_message("assistant", avatar=AVATAR_MAPS["model"]):
            message_placeholder = st.empty()
            generate_content_and_update_token(
                "聊天机器人",
                st.session_state.chat_model,
                [Part.from_text(prompt)],
                config,
                stream=True,
                placeholder=message_placeholder,
            )
    # endregion

# endregion

# region 多模态AI

elif menu == "多模态AI":
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
    sidebar_status = st.sidebar.empty()
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{format_token_count(st.session_state.total_token_count)}",
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

    with tabs[0]:
        st.subheader(":clipboard: :blue[示例或背景（可选）]", divider="rainbow", anchor=False)
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

        tab0_ex_btn_cols = st.columns([1, 1, 1, 1, 1, 1, 4])

        add_media_btn = tab0_ex_btn_cols[0].button(
            ":frame_with_picture:",
            help="✨ 将上传的图片或视频文件添加到案例中",
            key="add_media_btn",
        )
        add_text_btn = tab0_ex_btn_cols[1].button(
            ":memo:",
            help="✨ 将文本框内的内容添加到案例中",
            key="add_text_btn",
        )
        view_ex_btn = tab0_ex_btn_cols[2].button(
            ":mag_right:", help="✨ 查看全部样本", key="view_example"
        )
        del_text_btn = tab0_ex_btn_cols[3].button(
            ":wastebasket:",
            help="✨ 删除文本框内的文本",
            key="del_text_btn",
            on_click=clear_prompt,
            args=("ex_text_key",),
        )
        del_last_btn = tab0_ex_btn_cols[4].button(
            ":rewind:", help="✨ 删除案例中的最后一条样本", key="del_last_example"
        )
        cls_ex_btn = tab0_ex_btn_cols[5].button(
            ":arrows_counterclockwise:", help="✨ 删除全部样本", key="clear_example"
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
            st.session_state.multimodal_examples.append(
                {"mime_type": "text", "part": p}
            )
            view_example(st.session_state.multimodal_examples, examples_container)

        if del_last_btn:
            if len(st.session_state["multimodal_examples"]) > 0:
                st.session_state["multimodal_examples"].pop()
                view_example(st.session_state.multimodal_examples, examples_container)

        if cls_ex_btn:
            st.session_state["multimodal_examples"] = []
            view_example(st.session_state.multimodal_examples, examples_container)

        if view_ex_btn:
            st.subheader(
                f":clipboard: :blue[已添加的案例（{len(st.session_state.multimodal_examples)}）]",
                divider="rainbow",
                anchor=False,
            )
            examples_container.empty()
            view_example(st.session_state.multimodal_examples, examples_container)

    with tabs[1]:
        st.subheader(":bulb: :blue[提示词]", divider="rainbow", anchor=False)
        st.markdown(
            "请上传所需的多媒体文件，并在下方的文本框中输入您的提示词。完成后，请点击 `提交` 按钮以启动模型。如果您已添加示例，它们也将一同提交。"
        )
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
        tab0_btn_cols = st.columns([1, 1, 1, 7])
        # help="模型可以接受多个输入，以用作示例来了解您想要的输出。添加这些样本有助于模型识别模式，并将指定图片和响应之间的关系应用于新样本。这也称为少量样本学习。示例之间，添加'<>'符号用于分隔。"
        cls_btn = tab0_btn_cols[0].button(
            ":wastebasket:",
            help="✨ 清空提示词",
            key="clear_prompt",
            on_click=clear_prompt,
            args=("user_prompt_key",),
        )
        view_all_btn = tab0_btn_cols[1].button(
            ":mag_right:", help="✨ 查看全部样本", key="view_example-2"
        )
        submitted = tab0_btn_cols[2].button("提交")

        response_container = st.container()

        if view_all_btn:
            response_container.empty()
            contents = process_files_and_prompt(uploaded_files, prompt)
            response_container.subheader(
                f":clipboard: :blue[完整提示词（{len(contents)}）]",
                divider="rainbow",
                anchor=False,
            )
            view_example(contents, response_container)

        if submitted:
            if uploaded_files is None or len(uploaded_files) == 0:  # type: ignore
                st.warning("您是否忘记了上传图片或视频？")
            if not prompt:
                st.error("请添加提示词")
                st.stop()
            contents = process_files_and_prompt(uploaded_files, prompt)
            response_container.empty()
            col1, col2 = response_container.columns([1, 1])
            view_example(contents, col1)
            generate_content_from_files_and_prompt(contents, col2.empty())

# endregion

# region 多模态AI

elif menu == "示例教程":
    # region 边栏
    sidebar_status = st.sidebar.empty()
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{format_token_count(st.session_state.total_token_count)}",
        help=help_info,
    )
    # endregion

    # region 主页

    st.header("Vertex AI Gemini 示例", divider="rainbow", anchor=False)

    items_emoji = [
        ":book:",
        ":mega:",
        ":framed_picture:",
        ":film_frames:",
        ":bookmark_tabs:",
        ":mortar_board:",
    ]
    items = ["生成故事", "营销活动", "图像游乐场", "视频游乐场", "示例", "教程"]

    tabs = st.tabs([f"{emoji} {item}" for emoji, item in zip(items_emoji, items)])

    text_model = load_vertex_model("gemini-pro")
    vision_model = load_vertex_model("gemini-pro-vision")

    with tabs[0]:
        st.write("使用 Gemini Pro - 仅有文本模型")
        st.subheader(":blue[生成一个故事]", anchor=False)

        # Story premise
        character_name = st.text_input("输入角色名称：", key="character_name", value="七七")
        character_type = st.text_input("它是什么类型的角色？ ", key="character_type", value="狗")
        character_persona = st.text_input(
            "这个角色有什么性格？",
            key="character_persona",
            value="七七是一只非常黏人的比熊犬。",
        )
        character_location = st.text_input(
            "角色住在哪里？",
            key="character_location",
            value="山城重庆",
        )
        story_premise = st.multiselect(
            "故事前提是什么？ (可以选择多个)",
            ["爱", "冒险", "神秘", "恐怖", "喜剧", "科幻", "幻想", "惊悚片"],
            key="story_premise",
            default=["神秘", "喜剧"],
        )
        creative_control = st.radio(
            "选择创意级别：",
            ["低", "高"],
            key="creative_control",
            horizontal=True,
        )
        length_of_story = st.radio(
            "选择故事的长度:",
            ["短", "长"],
            key="length_of_story",
            horizontal=True,
        )

        if creative_control == "低":
            temperature = 0.30
        else:
            temperature = 0.95

        max_output_tokens = 2048

        prompt = f"""根据以下前提编写一个 {length_of_story} 故事：\n
角色名称: {character_name} \n
角色类型：{character_type} \n
角色性格：{character_persona} \n
角色位置：{character_location} \n
故事前提：{",".join(story_premise)} \n
如果故事“短”，则确保有 5 章，如果故事“长”，则确保有 10 章。
重要的一点是，每一章都应该基于上述前提生成。
首先介绍本书，然后介绍章节，之后逐一介绍每一章。 应该有一个合适的结局。
这本书应该有序言和结语。
        """
        config = {
            "temperature": 0.8,
            "max_output_tokens": 2048,
        }

        generate_t2t = st.button("生成我的故事", key="generate_t2t")
        if generate_t2t and prompt:
            # st.write(prompt)
            with st.spinner("使用 Gemini 生成您的故事..."):
                first_tab1, first_tab2, first_tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
                with first_tab1:
                    placeholder = st.empty()
                    generate_content_and_update_token(
                        "演示：生成故事",
                        text_model,
                        [Part.from_text(prompt)],
                        GenerationConfig(**config),
                        stream=True,
                        placeholder=placeholder,
                    )
                with first_tab2:
                    st.text(prompt)
                with first_tab3:
                    st.write("参数设置：")
                    st.write(config)

    with tabs[1]:
        st.write("使用 Gemini Pro - 仅有文本模型")
        st.subheader("生成您的营销活动")

        product_name = st.text_input("产品名称是什么？", key="product_name", value="ZomZoo")
        product_category = st.radio(
            "选择您的产品类别：",
            ["服装", "电子产品", "食品", "健康与美容", "家居与园艺"],
            key="product_category",
            horizontal=True,
        )
        st.write("选择您的目标受众：")
        target_audience_age = st.radio(
            "目标年龄：",
            ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
            key="target_audience_age",
            horizontal=True,
        )
        # target_audience_gender = st.radio("Target gender: \n\n",["male","female","trans","non-binary","others"],key="target_audience_gender",horizontal=True)
        target_audience_location = st.radio(
            "目标位置：",
            ["城市", "郊区", "乡村"],
            key="target_audience_location",
            horizontal=True,
        )
        st.write("选择您的营销活动目标：")
        campaign_goal = st.multiselect(
            "选择您的营销活动目标：",
            [
                "提高品牌知名度",
                "产生潜在客户",
                "推动销售",
                "提高品牌情感",
            ],
            key="campaign_goal",
            default=["提高品牌知名度", "产生潜在客户"],
        )
        if campaign_goal is None:
            campaign_goal = ["提高品牌知名度", "产生潜在客户"]
        brand_voice = st.radio(
            "选择您的品牌风格：",
            ["正式", "非正式", "严肃", "幽默"],
            key="brand_voice",
            horizontal=True,
        )
        estimated_budget = st.radio(
            "选择您的估计预算（人民币）：",
            ["1,000-5,000", "5,000-10,000", "10,000-20,000", "20,000+"],
            key="estimated_budget",
            horizontal=True,
        )

        prompt = f"""为 {product_name} 生成营销活动，该 {product_category} 专为年龄组：{target_audience_age} 设计。
目标位置是：{target_audience_location}。
主要目标是实现{campaign_goal}。
使用 {brand_voice} 的语气强调产品的独特销售主张。
分配总预算 {estimated_budget} 元【人民币】。
遵循上述条件，请确保满足以下准则并生成具有正确标题的营销活动：\n
- 简要描述公司、其价值观、使命和目标受众。
- 突出显示任何相关的品牌指南或消息传递框架。
- 简要概述活动的目的和目标。
- 简要解释所推广的产品或服务。
- 通过清晰的人口统计数据、心理统计数据和行为洞察来定义您的理想客户。
- 了解他们的需求、愿望、动机和痛点。
- 清楚地阐明活动的预期结果。
- 为了清晰起见，使用 SMART 目标（具体的、可衡量的、可实现的、相关的和有时限的）。
- 定义关键绩效指标 (KPI) 来跟踪进度和成功。
- 指定活动的主要和次要目标。
- 示例包括品牌知名度、潜在客户开发、销售增长或网站流量。
- 明确定义您的产品或服务与竞争对手的区别。
- 强调为目标受众提供的价值主张和独特优势。
- 定义活动信息所需的基调和个性。
- 确定您将用于接触目标受众的具体渠道。
- 清楚地说明您希望观众采取的期望行动。
- 使其具体、引人注目且易于理解。
- 识别并分析市场上的主要竞争对手。
- 了解他们的优势和劣势、目标受众和营销策略。
- 制定差异化战略以在竞争中脱颖而出。
- 定义您将如何跟踪活动的成功。
- 利用相关的 KPI 来衡量绩效和投资回报 (ROI)。
为营销活动提供适当的要点和标题。 不要产生任何空行。
非常简洁并切中要点。
        """
        config = {
            "temperature": 0.8,
            "max_output_tokens": 2048,
        }
        generate_t2t = st.button("生成我的活动", key="generate_campaign")
        if generate_t2t and prompt:
            second_tab1, second_tab2, second_tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            with st.spinner("使用 Gemini 生成您的营销活动..."):
                with second_tab1:
                    placeholder = st.empty()
                    generate_content_and_update_token(
                        "演示：营销活动",
                        text_model,
                        [Part.from_text(prompt)],
                        GenerationConfig(**config),
                        stream=True,
                        placeholder=placeholder,
                    )
                with second_tab2:
                    st.text(prompt)
                with second_tab3:
                    st.write(config)

    with tabs[2]:
        st.write("使用 Gemini Pro Vision - 多模态模型")
        image_undst, screens_undst, diagrams_undst, recommendations, sim_diff = st.tabs(
            [
                "家具推荐",
                "烤箱使用说明",
                "实体关系（ER）图",
                "眼镜推荐",
                "数学推理",
            ]
        )

        with image_undst:
            st.markdown(
                """在此演示中，您将看到一个场景（例如客厅），并将使用 Gemini 模型来执行视觉理解。 您将看到如何使用 Gemini 从家具选项列表中推荐一个项目（例如一把椅子）作为输入。 您可以使用 Gemini 推荐一把可以补充给定场景的椅子，并将从提供的列表中提供其选择的理由。
            """
            )

            room_image_uri = "gs://github-repo/img/gemini/retail-recommendations/rooms/living_room.jpeg"
            chair_1_image_uri = "gs://github-repo/img/gemini/retail-recommendations/furnitures/chair1.jpeg"
            chair_2_image_uri = "gs://github-repo/img/gemini/retail-recommendations/furnitures/chair2.jpeg"
            chair_3_image_uri = "gs://github-repo/img/gemini/retail-recommendations/furnitures/chair3.jpeg"
            chair_4_image_uri = "gs://github-repo/img/gemini/retail-recommendations/furnitures/chair4.jpeg"

            room_image_urls = (
                "https://storage.googleapis.com/" + room_image_uri.split("gs://")[1]
            )
            chair_1_image_urls = (
                "https://storage.googleapis.com/" + chair_1_image_uri.split("gs://")[1]
            )
            chair_2_image_urls = (
                "https://storage.googleapis.com/" + chair_2_image_uri.split("gs://")[1]
            )
            chair_3_image_urls = (
                "https://storage.googleapis.com/" + chair_3_image_uri.split("gs://")[1]
            )
            chair_4_image_urls = (
                "https://storage.googleapis.com/" + chair_4_image_uri.split("gs://")[1]
            )

            room_image = Part.from_uri(room_image_uri, mime_type="image/jpeg")
            chair_1_image = Part.from_uri(chair_1_image_uri, mime_type="image/jpeg")
            chair_2_image = Part.from_uri(chair_2_image_uri, mime_type="image/jpeg")
            chair_3_image = Part.from_uri(chair_3_image_uri, mime_type="image/jpeg")
            chair_4_image = Part.from_uri(chair_4_image_uri, mime_type="image/jpeg")

            st.image(room_image_urls, width=350, caption="客厅的图像")
            st.image(
                [
                    chair_1_image_urls,
                    chair_2_image_urls,
                    chair_3_image_urls,
                    chair_4_image_urls,
                ],
                width=200,
                caption=["椅子 1", "椅子 2", "椅子 3", "椅子 4"],
            )

            st.write("我们的期望：推荐一把与客厅既定形象相得益彰的椅子。")
            content = [
                "考虑以下椅子：",
                "椅子 1:",
                chair_1_image,
                "椅子 2:",
                chair_2_image,
                "椅子 3:",
                chair_3_image,
                "以及",
                "椅子 4:",
                chair_4_image,
                "\n" "对于每把椅子，请解释为什么它适合或不适合以下房间：",
                room_image,
                "只推荐所提供的房间，不推荐其他房间。 以表格形式提供您的建议，并以椅子名称和理由为标题列。",
            ]

            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            generate_image_description = st.button(
                "生成推荐", key="generate_image_description"
            )
            with tab1:
                if generate_image_description and content:
                    placeholder = st.empty()
                    with st.spinner("使用 Gemini 生成推荐..."):
                        new_contents = [
                            Part.from_text(item) if isinstance(item, str) else item
                            for item in content
                        ]
                        generate_content_and_update_token(
                            "演示：家具推荐",
                            vision_model,
                            new_contents,
                            GenerationConfig(
                                **gemini_pro_vision_generation_config,
                            ),
                            stream=True,
                            placeholder=placeholder,
                        )
            with tab2:
                st.write("使用的提示词：")
                st.text(content)
            with tab2:
                st.write("使用的参数：")
                st.write(None)

        with screens_undst:
            stove_screen_uri = (
                "gs://github-repo/img/gemini/multimodality_usecases_overview/stove.jpg"
            )
            stove_screen_url = (
                "https://storage.googleapis.com/" + stove_screen_uri.split("gs://")[1]
            )

            st.write("Gemini 能够从屏幕上的视觉元素中提取信息，可以分析屏幕截图、图标和布局，以全面了解所描绘的场景。")
            # cooking_what = st.radio("What are you cooking?",["Turkey","Pizza","Cake","Bread"],key="cooking_what",horizontal=True)
            stove_screen_img = Part.from_uri(stove_screen_uri, mime_type="image/jpeg")
            st.image(stove_screen_url, width=350, caption="烤箱的图像")
            st.write("我们的期望：提供有关重置此设备时钟的中文说明")
            prompt = """如何重置此设备上的时钟？ 提供中文说明。
    如果说明包含按钮，还要解释这些按钮的物理位置。
    """
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            generate_instructions_description = st.button(
                "生成指令", key="generate_instructions_description"
            )
            with tab1:
                placeholder = st.empty()
                if generate_instructions_description and prompt:
                    with st.spinner("使用 Gemini 生成指令..."):
                        new_contents = [stove_screen_img, Part.from_text(prompt)]
                        generate_content_and_update_token(
                            "烤箱使用说明演示",
                            vision_model,
                            new_contents,
                            GenerationConfig(**gemini_pro_vision_generation_config),
                            stream=True,
                            placeholder=placeholder,
                        )
            with tab2:
                st.write("使用的提示词：")
                st.text(prompt + "\n" + "input_image")
            with tab3:
                st.write("使用的参数：")
                st.write("默认参数")

        with diagrams_undst:
            er_diag_uri = (
                "gs://github-repo/img/gemini/multimodality_usecases_overview/er.png"
            )
            er_diag_url = (
                "https://storage.googleapis.com/" + er_diag_uri.split("gs://")[1]
            )

            st.write(
                "Gemini 的多模式功能使其能够理解图表并采取可操作的步骤，例如优化或代码生成。 以下示例演示了 Gemini 如何解读实体关系 (ER) 图。"
            )
            er_diag_img = Part.from_uri(er_diag_uri, mime_type="image/jpeg")
            st.image(er_diag_url, width=350, caption="Image of a ER diagram")
            st.write("我们的期望：记录此 ER 图中的实体和关系。")
            prompt = """记录此 ER 图中的实体和关系。"""
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            er_diag_img_description = st.button("生成！", key="er_diag_img_description")
            with tab1:
                if er_diag_img_description and prompt:
                    placeholder = st.empty()
                    new_contents = [er_diag_img, Part.from_text(prompt)]
                    with st.spinner("生成..."):
                        generate_content_and_update_token(
                            "演示：ER 图",
                            vision_model,
                            new_contents,
                            GenerationConfig(**gemini_pro_vision_generation_config),
                            stream=True,
                            placeholder=placeholder,
                        )
            with tab2:
                st.write("使用的提示词：")
                st.text(prompt + "\n" + "input_image")
            with tab3:
                st.write("使用的参数：")
                st.text("默认参数")

        with recommendations:
            compare_img_1_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/glasses1.jpg"
            compare_img_2_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/glasses2.jpg"

            compare_img_1_url = (
                "https://storage.googleapis.com/" + compare_img_1_uri.split("gs://")[1]
            )
            compare_img_2_url = (
                "https://storage.googleapis.com/" + compare_img_2_uri.split("gs://")[1]
            )

            st.write(
                """Gemini 能够进行图像比较并提供建议。 这在电子商务和零售等行业可能很有用。
                以下是选择哪副眼镜更适合不同脸型的示例："""
            )
            compare_img_1_img = Part.from_uri(compare_img_1_uri, mime_type="image/jpeg")
            compare_img_2_img = Part.from_uri(compare_img_2_uri, mime_type="image/jpeg")
            face_type = st.radio(
                "你是什么脸型？",
                ["椭圆形", "圆形", "方形", "心形", "钻石形"],
                key="face_type",
                horizontal=True,
            )
            output_type = st.radio(
                "选择输出类型",
                ["text", "table", "json"],
                key="output_type",
                horizontal=True,
            )
            st.image(
                [compare_img_1_url, compare_img_2_url],
                width=350,
                caption=["眼镜类型 1", "眼镜类型 2"],
            )
            st.write(f"我们的期望：建议哪种眼镜类型更适合 {face_type} 脸型")
            content = [
                f"""根据我的脸型，您为我推荐哪一款眼镜：{face_type}?
            我有一张 {face_type} 形状的脸。
            眼镜 1: """,
                compare_img_1_img,
                """
            眼镜 2: """,
                compare_img_2_img,
                f"""
            解释一下你是如何做出这个决定的。
            根据我的脸型提供您的建议，并以 {output_type} 格式对每个脸型进行推理。
            """,
            ]
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            compare_img_description = st.button("生成推荐", key="compare_img_description")
            with tab1:
                if compare_img_description and content:
                    with st.spinner("使用 Gemini 生成推荐..."):                        
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro, content
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
            with tab2:
                st.write("使用的提示词：")
                st.text(content)
            with tab3:
                st.write("使用的参数：")
                st.text("默认参数")

        with sim_diff:
            math_image_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/math_beauty.jpg"
            math_image_url = (
                "https://storage.googleapis.com/" + math_image_uri.split("gs://")[1]
            )
            st.write("Gemini 还可以识别数学公式和方程，并从中提取特定信息。 此功能对于生成数学问题的解释特别有用，如下所示。")
            math_image_img = Part.from_uri(math_image_uri, mime_type="image/jpeg")
            st.image(math_image_url, width=350, caption="Image of a math equation")
            st.markdown(
                f"""
    我们的期望：提出有关数学方程的问题如下：
    - 提取公式。
    - Pi 前面的符号是什么？ 这是什么意思？
    - 这是一个著名的公式吗？ 它有名字吗？
    """
            )
            prompt = """
    按照说明进行操作。
    用"$"将数学表达式括起来。
    使用一个表格，其中一行代表每条指令及其结果。

    指示：
    - 提取公式。
    - $\pi$ 前面的符号是什么？ 这是什么意思？
    - 这是一个著名的公式吗？ 它有名字吗？
    """
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            math_image_description = st.button("生成答案", key="math_image_description")
            with tab1:
                if math_image_description and prompt:
                    with st.spinner("使用 Gemini 生成公式答案..."):
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro,
                            [math_image_img, prompt],
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
            with tab2:
                st.write("使用的提示词：")
                st.text(content)
            with tab3:
                st.write("使用的参数：")
                st.text("默认参数")

    with tabs[3]:
        st.write("使用 Gemini Pro Vision - 多模态模型")

        vide_desc, video_tags, video_highlights, video_geoloaction = st.tabs(
            ["视频描述", "视频标签", "视频亮点", "视频地理位置"]
        )

        with vide_desc:
            st.markdown("""Gemini 还可以提供视频中发生的情况的描述：""")
            vide_desc_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/mediterraneansea.mp4"
            video_desc_url = (
                "https://storage.googleapis.com/" + vide_desc_uri.split("gs://")[1]
            )
            if vide_desc_uri:
                vide_desc_img = Part.from_uri(vide_desc_uri, mime_type="video/mp4")
                st.video(video_desc_url)
                st.write("我们的期望：生成视频的描述")
                prompt = """描述视频中发生的事情并回答以下问题：\n
    - 我在看什么？ \n
    - 我应该去哪里看？ \n
    - 世界上还有哪些像这样的前 5 个地方？
                """
                tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
                vide_desc_description = st.button("生成视频描述", key="vide_desc_description")
                with tab1:
                    if vide_desc_description and prompt:
                        with st.spinner("使用 Gemini 生成视频描述..."):
                            model = load_vertex_model("gemini-pro-vision")
                            placeholder = st.empty()
                            response = get_gemini_pro_vision_response(
                                st.session_state.multimodal_model_pro,
                                [prompt, vide_desc_img],
                            )
                            placeholder = st.empty()
                            # st.write(response)
                            view_stream_response(response, placeholder)
                            st.markdown("\n\n\n")
                with tab2:
                    st.write("使用的提示词：")
                    st.markdown(prompt + "\n" + "{video_data}")
                with tab3:
                    st.write("使用的参数：")
                    st.write("默认参数")

        with video_tags:
            st.markdown("""Gemini 还可以提取整个视频中的标签，如下所示：""")
            video_tags_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/photography.mp4"
            video_tags_url = (
                "https://storage.googleapis.com/" + video_tags_uri.split("gs://")[1]
            )
            if video_tags_url:
                video_tags_img = Part.from_uri(video_tags_uri, mime_type="video/mp4")
                st.video(video_tags_url)
                st.write("我们的期望：为视频生成标签")
                prompt = """仅使用视频回答以下问题：
    1. 视频里讲了什么？
    2. 视频中有哪些物体？
    3. 视频中的动作是什么？
    4. 为该视频提供5个最佳标签？
    以表格形式给出答案，问题和答案作为列。
                """
                tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
                video_tags_description = st.button("生成标签", key="video_tags_description")
                with tab1:
                    if video_tags_description and prompt:
                        with st.spinner("使用 Gemini 生成视频描述..."):
                            response = get_gemini_pro_vision_response(
                                st.session_state.multimodal_model_pro,
                                [prompt, video_tags_img],
                            )
                            placeholder = st.empty()
                            # st.write(response)
                            view_stream_response(response, placeholder)
                            st.markdown("\n\n\n")
                with tab2:
                    st.write("使用的提示词：")
                    st.write(prompt, "\n", "{video_data}")
                with tab3:
                    st.write("使用的参数：")
                    st.write("默认参数")

        with video_highlights:
            st.markdown("""下面是使用 Gemini 询问有关物体、人或上下文的问题的另一个示例，如下面有关 Pixel 8 的视频所示：""")
            video_highlights_uri = (
                "gs://github-repo/img/gemini/multimodality_usecases_overview/pixel8.mp4"
            )
            video_highlights_url = (
                "https://storage.googleapis.com/"
                + video_highlights_uri.split("gs://")[1]
            )
            if video_highlights_url:
                video_highlights_img = Part.from_uri(
                    video_highlights_uri, mime_type="video/mp4"
                )
                st.video(video_highlights_url)
                st.write("我们的期望：生成视频的亮点")
                prompt = """仅使用视频回答以下问题：
    视频中的女孩是什么职业？
    这里重点介绍了手机的哪些功能？
    用一段总结视频。
    以表格形式提供答案。
                """
                tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
                video_highlights_description = st.button(
                    "生成视频精彩片段", key="video_highlights_description"
                )
                with tab1:
                    if video_highlights_description and prompt:
                        with st.spinner("使用 Gemini 生成视频集锦..."):
                            response = get_gemini_pro_vision_response(
                                st.session_state.multimodal_model_pro,
                                [prompt, video_highlights_img],
                            )
                            placeholder = st.empty()
                            # st.write(response)
                            view_stream_response(response, placeholder)
                            st.markdown("\n\n\n")
                with tab2:
                    st.write("使用的提示词：")
                    st.write(prompt, "\n", "{video_data}")
                with tab3:
                    st.write("使用的参数：")
                    st.write(gemini_pro_vision_generation_config)

        with video_geoloaction:
            st.markdown("""即使在简短、细节丰富的视频中，Gemini 也能识别出位置。""")
            video_geoloaction_uri = (
                "gs://github-repo/img/gemini/multimodality_usecases_overview/bus.mp4"
            )
            video_geoloaction_url = (
                "https://storage.googleapis.com/"
                + video_geoloaction_uri.split("gs://")[1]
            )
            if video_geoloaction_url:
                video_geoloaction_img = Part.from_uri(
                    video_geoloaction_uri, mime_type="video/mp4"
                )
                st.video(video_geoloaction_url)
                st.markdown(
                    """我们的期望：\n
    回答视频中的以下问题：
    - 这个视频是关于什么的？
    - 你怎么知道是哪个城市？
    - 这是哪条街？
    - 最近的十字路口是什么？
                """
                )
                prompt = """仅使用视频回答以下问题：

    - 这个视频是关于什么的？
    - 你怎么知道是哪个城市？
    - 这是哪条街？
    - 最近的十字路口是什么？

    以表格形式回答以下问题，问题和答案作为列。
                """
                tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
                video_geoloaction_description = st.button(
                    "生成", key="video_geoloaction_description"
                )
                with tab1:
                    if video_geoloaction_description and prompt:
                        with st.spinner("使用 Gemini 生成位置标签..."):
                            response = get_gemini_pro_vision_response(
                                st.session_state.multimodal_model_pro,
                                [prompt, video_geoloaction_img],
                            )
                            placeholder = st.empty()
                            # st.write(response)
                            view_stream_response(response, placeholder)
                            st.markdown("\n\n\n")
                with tab2:
                    st.write("使用的提示词：")
                    st.write(prompt, "\n", "{video_data}")
                with tab3:
                    st.write("使用的参数：")
                    st.write(gemini_pro_vision_generation_config)

    # endregion

# endregion

# endregion
