import logging
import time

import streamlit as st
from vertexai.preview.generative_models import ResponseBlockedError

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
    page_title="聊天机器人",
    page_icon=":gemini:",
    layout="wide",
)
check_access(False)
configure_google_apis()

AVATAR_NAMES = ["user", "model"]
AVATAR_EMOJIES = ["👨‍🎓", "🤖"]
AVATAR_MAPS = {name: emoji for name, emoji in zip(AVATAR_NAMES, AVATAR_EMOJIES)}

if "examples_pair" not in st.session_state:
    st.session_state["examples_pair"] = []


if st.session_state.get("clear_example"):
    st.session_state["user_text_area"] = ""
    st.session_state["ai_text_area"] = ""

# endregion

# region 辅助函数


def init_chat():
    model = load_vertex_model("gemini-pro")
    history = []
    for user, ai in st.session_state["examples_pair"]:
        history.append({"role": "user", "parts": [user]})
        history.append({"role": "model", "parts": [ai]})
    st.session_state["chat_session"] = model.start_chat(history=history)
    st.session_state["chat_model"] = model


def add_chat_examples():
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
        init_chat()
    else:
        st.toast("示例对不能为空。")


def del_last_examples():
    if st.session_state["examples_pair"]:
        st.session_state["examples_pair"].pop()
        # st.write(st.session_state["examples_pair"])
        init_chat()


# endregion

# region 边栏

st.sidebar.markdown(
    """:rainbow[运行设置]\n
:gemini: 模型：Gemini Pro            
"""
)
st.sidebar.slider(
    "词元限制",
    key="max_output_tokens",
    min_value=32,
    max_value=8192,
    value=2048,
    step=32,
    help="""✨ 词元限制决定了一条提示的最大文本输出量。词元约为 4 个字符。默认值为 2048。""",
)
# 生成参数
st.sidebar.slider(
    "温度",
    min_value=0.00,
    max_value=1.0,
    key="temperature",
    value=0.6,
    step=0.1,
    help="✨ 温度可以控制词元选择的随机性。较低的温度适合希望获得真实或正确回复的提示，而较高的温度可能会引发更加多样化或意想不到的结果。如果温度为 0，系统始终会选择概率最高的词元。对于大多数应用场景，不妨先试着将温度设为 0.2。",
)

st.sidebar.slider(
    "Top K",
    key="top_k",
    min_value=1,
    max_value=40,
    value=40,
    step=1,
    help="""✨ Top-k 可更改模型选择输出词元的方式。
- 如果 Top-k 设为 1，表示所选词元是模型词汇表的所有词元中概率最高的词元（也称为贪心解码）。
- 如果 Top-k 设为 3，则表示系统将从 3 个概率最高的词元（通过温度确定）中选择下一个词元。
- Top-k 的默认值为 40。""",
)
st.sidebar.slider(
    "Top P",
    key="top_p",
    min_value=0.00,
    max_value=1.0,
    value=0.8,
    step=0.05,
    help="""✨ Top-p 可更改模型选择输出词元的方式。系统会按照概率从最高到最低的顺序选择词元，直到所选词元的概率总和等于 Top-p 的值。
- 例如，如果词元 A、B 和 C 的概率分别是 0.3、0.2 和 0.1，并且 Top-p 的值为 0.5，则模型将选择 A 或 B 作为下一个词元（通过温度确定）。
- Top-p 的默认值为 0.8。""",
)

st.sidebar.text_input(
    "添加停止序列",
    key="stop_sequences",
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
    on_click=add_chat_examples,
    disabled=len(st.session_state["examples_pair"]) >= 8,
    help="""✨ 聊天提示的示例是输入输出对的列表，它们演示给定输入的示例性模型输出。控制在8对以内。使用示例来自定义模型如何响应某些问题。
|用户示例|AI示例|
|:-|:-|
|火星有多少颗卫星？|火星有两个卫星，火卫一和火卫二。|
""",
)
sidebar_col2.button(
    ":heavy_minus_sign:",
    on_click=del_last_examples,
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
    init_chat()

with st.sidebar.expander("查看当前样例..."):
    if "chat_session" not in st.session_state:
        init_chat()
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

st.subheader(":robot_face: Google Gemini 聊天机器人")
if "chat_session" not in st.session_state:
    init_chat()

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
        "temperature": st.session_state["temperature"],
        "top_p": st.session_state["top_p"],
        "top_k": st.session_state["top_k"],
        "max_output_tokens": st.session_state["max_output_tokens"],
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
            st.session_state.total_token_count += st.session_state.current_token_count
            # 添加记录到数据库
            st.session_state.dbi.add_token_record(
                st.session_state.dbi.cache["phone_number"],
                "gemini-pro-chatbot",
                st.session_state.current_token_count,
            )
    except ResponseBlockedError as e:
        # 处理被阻止的消息
        st.toast("抱歉，您尝试发送的消息包含潜在不安全的内容，已被阻止。")
        # 删除最后一对会话
        st.session_state.chat_session.rewind()
    except Exception as e:
        # 处理其他类型的异常
        st.write(e)


msg = f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{format_token_count(st.session_state.total_token_count)}"
sidebar_status.markdown(msg, help=help_info)
# st.write(st.session_state.chat_session.history)

# endregion
