import time
import streamlit as st
from vertexai.language_models import ChatModel, InputOutputTextPair

from mypylib.authenticate import DbInterface
from mypylib.google_api import init_vertex

# region 认证及初始化

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

if "dbi" not in st.session_state:
    st.session_state["dbi"] = DbInterface()

if not st.session_state.dbi.is_vip_or_admin(st.session_state.user_id):
    st.error("您不是VIP用户，无法使用该功能")
    st.stop()

if "inited_vertex" not in st.session_state:
    init_vertex(st.secrets)
    st.session_state["inited_vertex"] = True

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# endregion

# region 常量

AVATAR_MAPS = {"user": "🧑‍💻", "assistant":"🤖"}

# endregion

# region 辅助函数


def init_chat():
    chat_model = ChatModel.from_pretrained("chat-bison")
    context = st.session_state["context_text_area"]
    examples = []
    for user, ai in st.session_state["examples_pair"]:
        examples.append(InputOutputTextPair(user, ai))
    st.session_state["chat"] = chat_model.start_chat(
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

# region 主页

st.set_page_config(
    page_title="聊天机器人",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="auto",
)

if "examples_pair" not in st.session_state:
    st.session_state["examples_pair"] = []


# 模型上下文 【按钮点击影响其他控件属性的标准做法】
if st.session_state.get("reset_btn"):
    st.session_state["context_text_area"] = ""

if st.session_state.get("clear_example"):
    st.session_state["user_text_area"] = ""
    st.session_state["ai_text_area"] = ""

st.sidebar.slider(
    "响应数量上限",
    key="candidate_count",
    min_value=1,
    max_value=4,
    value=1,
    step=1,
    help="""每个提示生成的模型响应数量上限。响应仍可能因安全过滤器或其他政策而被阻止。""",
)
st.sidebar.slider(
    "词元限制",
    key="max_output_tokens",
    min_value=64,
    max_value=4096,
    value=1024,
    step=64,
    help="""词元限制决定了一条提示的最大文本输出量。词元约为 4 个字符。默认值为 1024。""",
)
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

st.sidebar.text_area(
    "模型上下文",
    key="context_text_area",
    max_chars=1000,
    on_change=init_chat,
    # height=60,
    placeholder="你很诚实，从不说谎。 切勿编造事实，如果您不能 100% 确定，请回答您无法如实回答的原因。",
    help="""使用聊天提示中的上下文来自定义聊天模型的行为（可选）。
您可以使用上下文来执行以下操作：
- 指定模型可以和不能使用的单词。
- 指定要关注或避免的主题。
- 指定响应的风格、语气或格式。
- 假设一个人物、人物或角色。

|最佳实践|描述|示例|
|:-|:-|:-|
|给出聊天机器人要遵循的规则。|规则限制聊天机器人的行为。|你来自1700年代。|
|||1700年代以后你就什么都不知道了。|
|添加提醒以始终记住并遵循说明。|帮助聊天机器人在对话中遵循上下文中的说明。|在您回复之前，请注意、思考并记住此处设置的所有说明。|
|添加一条规则以减少幻觉。|帮助聊天机器人给出更真实的答案。|你很诚实，从不说谎。 切勿编造事实，如果您不能 100% 确定，请回答您无法如实回答的原因。|
""",
)

user_example = st.sidebar.text_area(
    "用户示例",
    key="user_text_area",
    max_chars=1000,
    # height=200,
    # placeholder=user_placeholder,
)
ai_example = st.sidebar.text_area(
    "AI示例",
    key=f"ai_text_area",
    max_chars=1000,
    # height=200,
    # placeholder=ai_placeholder,
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
    del st.session_state["messages"]
    init_chat()


# 主页面
st.title("🤖 聊天机器人")
info_container = st.empty()

if "messages" in st.session_state and st.session_state.messages:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar=AVATAR_MAPS[msg["role"]]):
            st.markdown(msg["content"])


if "chat" not in st.session_state:
    init_chat()

if prompt := st.chat_input("您的输入"):
    with st.chat_message("user", avatar=AVATAR_MAPS["user"]):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    parameters = {
        # 流式不支持
        "candidate_count": st.session_state[
            "candidate_count"
        ],  # The candidate_count parameter determines the maximum number of responses to return.
        "max_output_tokens": st.session_state[
            "max_output_tokens"
        ],  # Token limit determines the maximum amount of text output.
        "temperature": st.session_state[
            "temperature"
        ],  # Temperature controls the degree of randomness in token selection.
        "top_p": st.session_state[
            "top_p"
        ],  # Tokens are selected from most probable to least until the sum of their probabilities equals the top_p value.
        "top_k": st.session_state[
            "top_k"
        ],  # A top_k of 1 means the selected token is the most probable among all tokens.
    }
    # st.write("参数",parameters)
    response = st.session_state.chat.send_message(message=prompt, **parameters)
    with st.chat_message("user", avatar=AVATAR_MAPS["assistant"]):
        st.markdown(response.text)
    st.session_state.messages.append({"role": "assistant", "content": response.text})

# endregion
