import hashlib
import json
import os
import random
from pathlib import Path
from typing import List, Tuple

# import google.generativeai as palm
import streamlit as st

from mypylib.azure_speech import synthesize_speech_to_file
from mypylib.azure_translator import translate
from mypylib.constants import CEFR_LEVEL_MAPS, NAMES, TOPICS
from mypylib.google_api import generate_text
from mypylib.st_utils import authenticate_and_configure_services

# region 认证及初始化

st.set_page_config(
    page_title="口语练习",
    page_icon="🎤",
    layout="wide",
)

authenticate_and_configure_services()

# endregion

# region 常量
CURRENT_CWD: Path = Path(__file__).parent.parent
VOICES_FP = CURRENT_CWD / "resource" / "voices.json"

audio_dir = CURRENT_CWD / "resource" / "audio_data"
dialogue_dir = audio_dir / "dialogue"
if not os.path.exists(dialogue_dir):
    os.makedirs(dialogue_dir, exist_ok=True)


# silent_fp = str(audio_dir / "silent.wav")

model = "models/text-bison-001"
language = "American English"

AVATAR_NAMES = ["user", "assistant"]
AVATAR_EMOJIES = [":boy:", ":girl:"]
AVATAR_MAPS = {name: emoji for name, emoji in zip(AVATAR_NAMES, AVATAR_EMOJIES)}

# endregion


# region 函数


@st.cache_data(ttl=60 * 60 * 24, show_spinner="Fetch data from Azure translations...")
def get_translation(text):
    if text == "":
        return ""
    res = translate(
        text,
        "en-US",
        ["zh-CN"],
        st.secrets["Microsoft"]["TRANSLATOR_TEXT_SUBSCRIPTION_KEY"],
        st.secrets["Microsoft"]["TRANSLATOR_TEXT_REGION"],
    )
    return res[0]["translations"][0]["text"]


def get_dialogue_audio_file_path(idx, voice):
    return str(
        dialogue_dir / f"{st.session_state.user_info['user_id']}-{idx}-{voice}.mp3"
    )


@st.cache_data(ttl=60 * 60, show_spinner="从 Azure 语音库合成语音...")
def synthesize_speech(text, idx, voice):
    listen_fp = get_dialogue_audio_file_path(idx, voice)
    synthesize_speech_to_file(
        text,
        listen_fp,
        st.secrets["Microsoft"]["SPEECH_KEY"],
        st.secrets["Microsoft"]["SPEECH_REGION"],
        voice,
    )


def get_conversations(completion, boy, girl):
    context = completion.result.splitlines()
    # st.write(context)
    dialogue = []
    for c in context:
        if (
            c.startswith(f"{boy}:")
            or c.startswith(f"**{boy}:")
            or c.startswith(f"{girl}:")
            or c.startswith(f"**{girl}:")
        ):
            dialogue.append(c)
    return dialogue


# endregion

# region 基础配置


if "dialogue_context" not in st.session_state:
    st.session_state["dialogue_context"] = []
if "dialogue_idx" not in st.session_state:
    st.session_state["dialogue_idx"] = -1
if "dialogue_tgt" not in st.session_state:
    st.session_state["dialogue_tgt"] = {}
if "audio_fp" not in st.session_state:
    st.session_state["audio_fp"] = {}


def reset_session():
    st.session_state["dialogue_context"] = []
    st.session_state["dialogue_idx"] = -1
    st.session_state["dialogue_tgt"] = {}
    st.session_state["audio_fp"] = {}
    files = dialogue_dir.glob(f"{st.session_state.user_info['user_id']}-*.mp3")
    for f in files:
        # print(f)
        os.remove(f)


def on_voice_changed():
    st.session_state["audio_fp"] = {}


# endregion

# region 边栏
with open(VOICES_FP, "r", encoding="utf-8") as f:
    voices = json.load(f)["en-US"]

m_voices = [v for v in voices if v[1] == "Male"]
fm_voices = [v for v in voices if v[1] == "Female"]
sidebar_cols = st.sidebar.columns(2)
boy = sidebar_cols[0].selectbox(
    "男方",
    NAMES["en-US"]["male"],
    key="first_party",
    help="男方姓名",
)
m_voice_style: Tuple = sidebar_cols[0].selectbox(
    "合成男声风格",
    m_voices,
    on_change=on_voice_changed,
    help="选择您喜欢的合成男声语音风格",
    format_func=lambda x: f"{x[2]}",  # type: ignore
)

girl = sidebar_cols[1].selectbox(
    "女方",
    NAMES["en-US"]["female"],
    key="second_party",
    help="女方姓名",
)
fm_voice_style: Tuple = sidebar_cols[1].selectbox(
    "合成女声风格",
    fm_voices,
    on_change=on_voice_changed,
    help="选择您喜欢的合成女声语音风格",
    format_func=lambda x: f"{x[2]}",  # type: ignore
)


level = st.sidebar.selectbox(
    "语言熟练程度",
    CEFR_LEVEL_MAPS.keys(),
    on_change=reset_session,
    key="dialogue_level",
    help="根据选择的语言熟练程度,系统会生成匹配的不同难度对话场景进行练习",
)
topic = st.sidebar.selectbox(
    "主题",
    TOPICS["zh-CN"],
    key="topic",
    on_change=reset_session,
    help="选择对话主题,系统会生成匹配的对话场景进行练习",
)

en_level = CEFR_LEVEL_MAPS.get(level, "中高级")  # type: ignore
en_topic = TOPICS["en-US"][TOPICS["zh-CN"].index(topic)]  # type: ignore
# st.sidebar.info(f"Selected: {en_topic}")


btn_cols = st.sidebar.columns(3)
gen_btn = btn_cols[0].button(
    "生成",
    help="根据选择的语言熟练程度和主题,系统会生成匹配的对话场景进行练习",
)
view_btn = btn_cols[1].button("查看", help="查看完整对话场景")
cls_btn = btn_cols[2].button(":arrows_counterclockwise:", help="重置对话场景")
# endregion

# region 事件


# endregion


# region 主页
container = st.container()
st.markdown(
    """#### 口语练习场景介绍

口语练习是提高英语口语能力的重要途径。本系统提供了丰富的口语练习场景，可以帮助您在真实的语境中练习口语。
"""
)

# st.markdown(st.session_state["dialogue_context"])

if gen_btn:
    sub_prompt = f"""Please generate 10 sub-topics related to "{en_topic}" and output them in list form"""
    sub_completion = generate_text(
        prompt=sub_prompt,
        temperature=1.0,
        top_p=0.95,
        # 增加随机性
        candidate_count=4,
        max_output_tokens=400,
    )
    sub_topic = random.choice(sub_completion.candidates)
    sub_topic = random.choice(sub_topic["output"].splitlines()).split(".")[1]

    # 生成对话
    prompt = f"""
        Please use {language} to simulate a conversation between {boy} and {girl} about "{sub_topic}". Please note that the actual language level of both parties is {en_level}, and the simulation content, word choice and sentence making must match their level. The word count should be no less than 200 words and no more than 400 words.
    """
    completion = generate_text(
        prompt=prompt,
        temperature=1.0,
        # The maximum length of the response
        max_output_tokens=400,
    )
    st.session_state["dialogue_context"] = get_conversations(completion, boy, girl)
    st.session_state["dialogue_idx"] = 0
    # 测试用
    # st.session_state["dialogue_context"] = ["hello", "world", "translate"]

if cls_btn:
    reset_session()


def view(placeholder):
    idx = st.session_state["dialogue_idx"]
    if idx >= 0 and idx < len(st.session_state["dialogue_context"]):
        with placeholder:
            src = st.session_state["dialogue_context"][idx]
            placeholder.markdown(src)
            tgt = st.session_state["dialogue_tgt"].get(idx, "")
            placeholder.markdown(tgt)
            # fmt = "audio/wav"
            fmt = "audio/mp3"
            fp = st.session_state["audio_fp"].get(idx, "")
            if fp:
                placeholder.audio(fp, format=fmt)


st.divider()
placeholder = st.container()
view(placeholder)
st.divider()


def on_t_btn_click():
    idx = st.session_state["dialogue_idx"]
    if idx >= 0 and idx < len(st.session_state["dialogue_context"]):
        src = st.session_state["dialogue_context"][idx]
        st.session_state["dialogue_tgt"][idx] = get_translation(src)


def on_s_btn_click():
    idx = st.session_state["dialogue_idx"]
    voice_style = m_voice_style if idx % 2 == 0 else fm_voice_style
    if idx >= 0 and idx < len(st.session_state["dialogue_context"]):
        src = st.session_state["dialogue_context"][idx]
        audio_fp = get_dialogue_audio_file_path(
            st.session_state["dialogue_idx"], voice_style[0]
        )
        synthesize_speech(src, st.session_state["dialogue_idx"], voice_style[0])
        st.session_state["audio_fp"][idx] = audio_fp


def on_p_btn_click():
    # print("on_p_btn_click", st.session_state["dialogue_idx"])
    st.session_state["dialogue_idx"] -= 1


def on_n_btn_click():
    # print("on_n_btn_click", st.session_state["dialogue_idx"])
    st.session_state["dialogue_idx"] += 1


cols = st.columns(5)

cols[1].button(
    "翻译 :mag:",
    on_click=on_t_btn_click,
    # args=(placeholder,),
    key="translate",
    disabled=st.session_state["dialogue_idx"] < 0,
    help="将对话内容翻译成中文",
)
cols[2].button(
    "合成 :sound:",
    key="speech",
    on_click=on_s_btn_click,
    # args=(placeholder,),
    disabled=st.session_state["dialogue_idx"] < 0,
    help="将对话内容合成语音",
)
cols[3].button(
    "向前 ⬅️",
    on_click=on_p_btn_click,
    key="prev",
    disabled=st.session_state["dialogue_idx"] <= 0,
    help="上一条对话",
)
cols[4].button(
    "向后 ➡️",
    key="next",
    on_click=on_n_btn_click,
    disabled=st.session_state["dialogue_idx"]
    == len(st.session_state["dialogue_context"]) - 1,
    help="下一条对话",
)

if view_btn:
    with container:
        st.markdown("#### 对话场景")
        for d in st.session_state["dialogue_context"]:
            st.markdown(d)
        st.divider()
# endregion

# region 具体指导
expander = st.expander("查看更多...")
expander.markdown(
    """
##### 如何使用
                  
1. 选择👈"语言熟练程度"和"主题"。根据您的英语水平和需要，选择合适的"语言熟练程度"和"主题"。
2. 点击👈"生成"按钮。AI将生成匹配的对话场景。
3. 点击👈"查看"按钮。查看当前完整的对话场景。
4. 点击👆"翻译"按钮。将当前对话内容翻译成目标语言。
5. 点击👆"合成"按钮。将当前对话内容合成语音。

##### 注意事项

- 选择合适的语言熟练程度和主题，可以帮助您获得更好的练习效果。
- 在练习时，要注意模仿对话中的语音、语调和发音。
- 可以与朋友或同学一起练习，以提高互动性。

##### 具体指导
以下是一些具体的指导建议：

- 在选择语言熟练程度时，可以参考以下标准：
    - 初级：能够理解简单的句子和日常用语。
    - 中级：能够理解日常对话和表达自己的想法。
    - 高级：能够流利地进行日常交流。
- 在选择主题时，可以根据自己的兴趣和需要选择。以下是一些常见的主题：
    - 社交：介绍自己、问候、道别等。
    - 旅行：询问路线、订酒店、购物等。
    - 工作：面试、讨论工作等。
    - 学习：问问题、回答问题等。
- 在练习时，可以先自己练习一遍，然后与朋友或同学一起练习。在练习时，要注意以下几点：
    - 注意发音和语调。
    - 注意语速和流利度。
    - 注意使用适当的词汇和表达。                                                                        
"""
)
# endregion
