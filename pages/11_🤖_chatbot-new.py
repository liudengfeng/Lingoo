import time

import google.generativeai as genai
import streamlit as st
from vertexai.preview.generative_models import ChatSession, GenerativeModel
from mypylib.streamlit_helper import authenticate, check_and_force_logout
from mypylib.google_gemini import SAFETY_SETTINGS

# import vertexai
# from vertexai.preview.generative_models import GenerativeModel, Part
# 注意 ：对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。
# response.usage_metadata.total_token_count

# region 页面设置

st.set_page_config(
    page_title="聊天机器人",
    page_icon="🤖",
    layout="wide",
)

# endregion

# region 辅助函数


def init_chat():
    model = genai.GenerativeModel(
        model_name="gemini-pro",
        generation_config=generation_config,
        safety_settings=SAFETY_SETTINGS,
    )
    context = st.session_state["context_text_area"]
    examples = []
    for user, ai in st.session_state["examples_pair"]:
        examples.append(InputOutputTextPair(user, ai))
    st.session_state["chat"] = model.start_chat(
        context=context,
        examples=examples,
    )


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


def del_chat_examples():
    if st.session_state["examples_pair"]:
        st.session_state["examples_pair"].pop()
        # st.write(st.session_state["examples_pair"])
        init_chat()


# endregion


# region 边栏

st.sidebar.markdown(
    """:rainbow[运行设置]\n
🔯 模型：Gemini Pro            
"""
)
sidebar_status = st.sidebar.empty()

st.sidebar.slider(
    "词元限制",
    key="max_output_tokens",
    min_value=32,
    max_value=2048,
    value=1024,
    step=32,
    help="""词元限制决定了一条提示的最大文本输出量。词元约为 4 个字符。默认值为 1024。""",
)
st.sidebar.info("对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。", icon="✨")
# 生成参数
st.sidebar.slider(
    "温度",
    min_value=0.00,
    max_value=1.0,
    key="temperature",
    value=0.6,  # st.session_state["model_temperature"],
    step=0.1,
    help="温度可以控制词元选择的随机性。较低的温度适合希望获得真实或正确回复的提示，而较高的温度可能会引发更加多样化或意想不到的结果。如果温度为 0，系统始终会选择概率最高的词元。对于大多数应用场景，不妨先试着将温度设为 0.2。",
)

st.sidebar.slider(
    "Top K",
    key="top_k",
    min_value=1,
    max_value=40,
    value=20,
    step=1,
    help="""Top-k 可更改模型选择输出词元的方式。
- 如果 Top-k 设为 1，表示所选词元是模型词汇表的所有词元中概率最高的词元（也称为贪心解码）。
- 如果 Top-k 设为 3，则表示系统将从 3 个概率最高的词元（通过温度确定）中选择下一个词元。
- Top-k 的默认值为 40。""",
)
st.sidebar.slider(
    "Top P",
    key="top_p",
    min_value=0.00,
    max_value=1.0,
    value=0.6,
    step=0.05,
    help="""Top-p 可更改模型选择输出词元的方式。系统会按照概率从最高到最低的顺序选择词元，直到所选词元的概率总和等于 Top-p 的值。
- 例如，如果词元 A、B 和 C 的概率分别是 0.3、0.2 和 0.1，并且 Top-p 的值为 0.5，则模型将选择 A 或 B 作为下一个词元（通过温度确定）。
- Top-p 的默认值为 0.8。""",
)


user_example = st.sidebar.text_area(
    "用户示例",
    key="user_text_area",
    max_chars=1000,
)
ai_example = st.sidebar.text_area(
    "AI示例",
    key="ai_text_area",
    max_chars=1000,
)

sidebar_col1, sidebar_col2, sidebar_col3, sidebar_col4 = st.sidebar.columns(4)

sidebar_col1.button(
    "➕",
    on_click=add_chat_examples,
    disabled=len(st.session_state["examples_pair"]) >= 8,
    help="""聊天提示的示例是输入输出对的列表，它们演示给定输入的示例性模型输出。控制在8对以内。使用示例来自定义模型如何响应某些问题。
|用户示例|AI示例|
|:-|:-|
|火星有多少颗卫星？|火星有两个卫星，火卫一和火卫二。|
""",
)
sidebar_col2.button(
    "➖",
    on_click=del_chat_examples,
    disabled=len(st.session_state["examples_pair"]) <= 0,
    help="删除最后一对示例",
)
sidebar_col3.button(
    "🗑️",
    key="clear_example",
    help="清除当前示例对",
)

if sidebar_col4.button("🔄", key="reset_btn", help="重新设置上下文、示例，开始新的对话"):
    st.session_state["examples_pair"] = []
    # 删除对象
    del st.session_state["chat_messages"]
    init_chat()

# endregion

authenticate(st)
check_and_force_logout(st, sidebar_status)

# def multiturn_generate_content():
#     config = {"max_output_tokens": 2048, "temperature": 0.9, "top_p": 1}
#     model = GenerativeModel("gemini-pro")
#     chat = model.start_chat()
#     response = chat.send_message("""你好""", generation_config=config)
#     # st.write(response.usage_metadata.total_token_count)  # type: ignore
#     st.write(response.text)
#     total_token_count = response._raw_response.usage_metadata
#     st.write(total_token_count.total_token_count)


# model = genai.GenerativeModel("gemini-pro")
# response = model.generate_content("生活的意义是什么？")
# st.markdown(response.text)
