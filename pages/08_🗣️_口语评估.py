import hashlib
import json
import os
import time
import wave
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from streamlit_mic_recorder import mic_recorder

from mypylib.authenticate import DbInterface
from mypylib.azure_speech import (
    pronunciation_assessment_with_content_assessment,
    synthesize_speech_to_file,
)
from mypylib.azure_translator import language_detect
from mypylib.constants import CEFR_LEVEL_MAPS, LAN_MAPS, TOPICS
from mypylib.google_api import init_vertex, generate_english_topics
from mypylib.html_constants import STYLE, TIPPY_JS
from mypylib.nivo_charts import gen_radar
from mypylib.word_utils import audio_autoplay_elem

# region 认证及初始化

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

if "dbi" not in st.session_state:
    st.session_state["dbi"] = DbInterface()

if not st.session_state.dbi.is_service_active(st.session_state["user_id"]):
    st.error("非付费用户，无法使用此功能。")
    st.stop()

if st.secrets["env"] in ["streamlit", "azure"]:
    if "inited_vertex" not in st.session_state:
        init_vertex(st.secrets)
        st.session_state["inited_vertex"] = True
else:
    st.error("非云端环境，无法使用 Vertex AI")
    st.stop()

# endregion

# region 常量

current_cwd: Path = Path(__file__).parent.parent
voices_fp = current_cwd / "resource" / "voices.json"
audio_dir = current_cwd / "resource" / "audio_data"

if not os.path.exists(audio_dir):
    os.makedirs(audio_dir, exist_ok=True)

# 使用临时文件
replay_fp = os.path.join(audio_dir, f"{st.session_state.user_id}-tab2-replay.wav")
listen_fp = os.path.join(audio_dir, f"{st.session_state.user_id}-tab2-listen.wav")

# region templates

WORD_TOOLTIP_TEMPLATE = """\
<table>\
    <tr>\
        <td colspan="{n}">{word_score}</td>\
    </tr>\
    <tr>\
        {phoneme_cols}\
    </tr>\
    <tr>\
        {score_cols}\
    </tr>\
</table>\
"""

BADGE_TEMPLATE = """
<button type="button" class="btn btn-{btn_class}" data-bs-toggle="tooltip" data-bs-placement="top"
        data-bs-custom-class="custom-tooltip"
        data-bs-title="{title}">
  {label} <span class="badge text-bg-{color}">{num}</span>
</button>
"""

# BTN_TEMPLATE = """
# <button type="button" class="btn {btn_class}"
#         data-tippy-content="{title}">
#   {label}
# </button>
# """
BTN_TEMPLATE = """
<button type="button" class="btn {btn_class}" data-bs-placement="top"
        data-tippy-content="{title}">
  {label}
</button>
"""

# endregion

# endregion

# region 会话状态

if "assessment_tb2" not in st.session_state:
    st.session_state["assessment_tb2"] = {}

if "tab2_topics" not in st.session_state:
    st.session_state["tab2_topics"] = []

# endregion

# region 函数


def reset_topics():
    level = st.session_state["ps_level"]
    category = st.session_state["ps_category"]
    st.session_state["tab2_topics"] = generate_english_topics(
        "测试英语口语水平", category, level
    )


@st.cache_data
def get_synthesize_speech(text, voice):
    synthesize_speech_to_file(
        text,
        listen_fp,
        st.secrets["Microsoft"]["SPEECH_KEY"],
        st.secrets["Microsoft"]["SPEECH_REGION"],
        voice,
    )


def update_mav(audio):
    # audio is the variable containing the audio data
    with wave.open(replay_fp, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(audio["sample_width"])
        wav_file.setframerate(audio["sample_rate"])
        wav_file.writeframes(audio["bytes"])


def get_bg_color(score):
    if score < 60:
        return "bg-danger"
    elif score < 80:
        return "bg-warning"
    else:
        return "bg-success"


def get_cp_color(score):
    if score < 60:
        return "#c02a2a"
    elif score < 80:
        return "yellow"
    else:
        return "green"


def generate_score_legend():
    """
    Returns an HTML string representing a score legend for Tippy game.

    The legend displays three color-coded ranges of scores:
    - 0 ~ 59: red
    - 60 ~ 79: yellow
    - 80 ~ 100: green

    Returns:
    str: An HTML string representing the score legend.
    """
    return """\
<div style="display: flex; align-items: center;">\
    <div style="width: 12px; height: 12px; background-color: #c02a2a; margin-right: 6px; margin-left: 6px;"></div>\
    <span>0 ~ 59</span>\
    <div style="width: 12px; height: 12px; background-color: yellow; margin-right: 6px;margin-left: 6px;"></div>\
    <span>60 ~ 79</span>\
    <div style="width: 12px; height: 12px; background-color: green; margin-right: 6px;margin-left: 6px;"></div>\
    <span>80 ~ 100</span>\
</div>\
"""


def generate_word_tooltip(word) -> str:
    """
    生成单词的工具提示。

    Args:
        word (str): 单词的字符串。
        definition (str): 单词的定义字符串。

    Returns:
        tooltip (str): 包含单词和定义的HTML工具提示字符串。
    """
    res = ""
    n = len(word.phonemes)
    word_score = f"{word.word} : {int(word.accuracy_score)}"
    phoneme_cols = """ """.join(
        [f"""<td>{p.phoneme}&nbsp;</td>""" for p in word.phonemes]
    )
    score_cols = """ """.join(
        [f"""<td>{int(p.accuracy_score)}&nbsp;</td>""" for p in word.phonemes]
    )
    res = WORD_TOOLTIP_TEMPLATE.format(
        n=n, word_score=word_score, phoneme_cols=phoneme_cols, score_cols=score_cols
    )
    return res


# region 标头

MD_BADGE_MAPS = OrderedDict(
    {
        "None": ("green", "发音优秀", "发音优秀的字词", "success"),
        "Mispronunciation": ("orange", "发音错误", "说得不正确的字词", "warning"),
        # "Omission": ("grey", "遗漏字词", "脚本中已提供，但未说出的字词", "secondary"),
        # "Insertion": ("red", "插入内容", "不在脚本中但在录制中检测到的字词", "danger"),
        "UnexpectedBreak": ("violet", "意外中断", "同一句子中的单词之间未正确暂停", "info"),
        "MissingBreak": ("blue", "缺少停顿", "当两个单词之间存在标点符号时，词之间缺少暂停", "light"),
        "Monotone": ("rainbow", "单调发音", "这些单词正以平淡且不兴奋的语调阅读，没有任何节奏或表达", "dark"),
    }
)

MD_BADGE_TEMPLATE = """
<button type="button" class="btn btn-{btn_class}" data-bs-toggle="tooltip" data-bs-placement="top"
        data-bs-custom-class="custom-tooltip"
        data-bs-title="{title}">
  {label} <span class="badge text-bg-{color}">{num}</span>
</button>
"""


def view_md_badges():
    assessment = st.session_state["assessment_tb2"]
    cols = st.columns(len(MD_BADGE_MAPS.keys()) + 2)
    error_counts = assessment.get("error_counts", {})
    for i, t in enumerate(MD_BADGE_MAPS.keys()):
        num = f"{error_counts.get(t,0):3d}"
        body = f"""{MD_BADGE_MAPS[t][1]}({num})"""
        cols[i].markdown(
            f""":{MD_BADGE_MAPS[t][0]}[{body}]""",
            help=MD_BADGE_MAPS[t][2],
        )


# endregion


# region 单词发音

MD_BTN_TEMPLATE = """
<button class="btn-{btn_class}" data-tippy-content="{title}">
  {label}
</button>
"""


def fmt_word(text: str, err_type: str):
    """
    Formats a word based on the error type.

    Args:
        text (str): The word to format.
        err_type (str): The type of error.

    Returns:
        str: The formatted word.
    """
    t = err_type.lower()
    match t:
        case "mispronunciation":
            return f"""<span class="text-decoration-underline">{text}</span>"""
        case "omission":
            return f"""[{text}]"""
        case "pause":
            return f"""[{text}]"""
        case "insertion":
            return f"""<span class="text-decoration-line-through">{text}</span>"""
        case "interruption":
            return f"""<span class="text-decoration-line-through">[{text}]</span>"""
        case "monotone":
            return f"""<span class="text-decoration-overline">[{text}]</span>"""
        case _:
            return f"""{text}"""


def view_word_pronunciation():
    assessment = st.session_state["assessment_tb2"]
    words_list = assessment.get("words_list", [])
    html = ""
    for word in words_list:
        error_type = f"{word.error_type}"
        # print(error_type)
        # btn_class = (
        #     f"""{MD_BADGE_MAPS[error_type][3]}""" if error_type != "success" else ""
        # )
        btn_class = f"""{MD_BADGE_MAPS[error_type][3]}"""
        label = fmt_word(word.word, error_type)
        # 解决单引号、双引号问题
        title = generate_word_tooltip(word).replace("'", "&#39;").replace('"', "&quot;")
        btn = MD_BTN_TEMPLATE.format(
            btn_class=btn_class,
            title=title,
            label=label,
        )
        # st.write(btn)
        html += btn
    html = f"""<p>{html}</p>"""
    components.html(STYLE + html + TIPPY_JS, height=300, scrolling=True)


# endregion

# region 雷达图


def view_radar():
    cols = st.columns(2)
    # 雷达图
    item_1 = {
        "pronunciation_score": "发音总评分",
        "accuracy_score": "准确性评分",
        "completeness_score": "完整性评分",
        "fluency_score": "流畅性评分",
        "prosody_score": "韵律分数",
    }
    data_1 = {key: st.session_state.assessment_tb2.get(key, 0) for key in item_1.keys()}
    with cols[0]:
        gen_radar(data_1, item_1, 320)

    content_result = st.session_state.assessment_tb2.get("content_result", {})
    item_2 = {
        "content_score": "内容分数",
        "grammar_score": "语法分数",
        "vocabulary_score": "词汇分数",
        "topic_score": "主题分数",
    }
    data_2 = {key: getattr(content_result, key, 0) for key in item_2.keys()}
    data_2["content_score"] = (
        data_2["grammar_score"] + data_2["vocabulary_score"] + data_2["topic_score"]
    ) / 3
    with cols[1]:
        gen_radar(data_2, item_2, 320)


# endregion

# region 发音评估报告


def view_report():
    # 发音评估报告
    view_md_badges()
    st.divider()
    view_word_pronunciation()
    view_radar()


# endregion


def view_score_legend(progress_cols, add_spinner=False):
    with progress_cols[0]:
        st.markdown(
            "**发音分数**",
            help="表示给定语音发音质量的总体分数。它是从 AccuracyScore、FluencyScore、CompletenessScore、Weight 按权重聚合的。",
        )
    with progress_cols[1]:
        st.markdown(
            "准确性评分",
            help="语音的发音准确性。准确性表示音素与母语说话人的发音的匹配程度。字词和全文的准确性得分是由音素级的准确度得分汇总而来。",
        )
    with progress_cols[2]:
        st.markdown(
            "完整性评分",
            help="语音的完整性，按发音单词与输入引用文本的比率计算。",
        )
    with progress_cols[3]:
        st.markdown(
            "流畅性评分",
            help="给定语音的流畅性。流畅性表示语音与母语说话人在单词间的停顿上有多接近。",
        )
    with progress_cols[4]:
        st.markdown(
            "韵律分数",
            help="给定语音的韵律。韵律指示给定语音的性质，包括重音、语调、语速和节奏。",
        )
    score_legend = generate_score_legend()
    # if add_spinner:
    #     score_legend += "<hr>"
    components.html(STYLE + score_legend)


# endregion

# region 页配置

st.set_page_config(
    page_title="评估发音与对话",
    page_icon="🗣️",
    layout="wide",
)

if not st.session_state.dbi.is_service_active(st.session_state["user_id"]):
    st.error("您尚未付费，无法使用此功能。")
    st.stop()

# endregion

# region 边栏

language = "en-US"

with open(voices_fp, "r", encoding="utf-8") as f:
    names = json.load(f)[language]
voice_style: Any = st.sidebar.selectbox(
    "合成语音风格", names, format_func=lambda x: f"{x[2]}【{x[1]}】"
)

level_selectbox = st.sidebar.selectbox(
    "您当前的英语水平",
    CEFR_LEVEL_MAPS.keys(),
    format_func=lambda x: CEFR_LEVEL_MAPS[x],
    on_change=reset_topics,
    key="ps_level",
    help="场景话题会根据您的选择来匹配难度",
)
topic_selectbox = st.sidebar.selectbox(
    "主题",
    TOPICS["zh-CN"],
    key="ps_category",
    on_change=reset_topics,
    help="选择主题，AI生成话题供您选择",
)


# endregion

# region 事件


def reset_tb2():
    # get_synthesize_speech.clear()
    st.session_state["assessment_tb2"] = {}
    st.session_state["text_tb2"] = ""
    if os.path.exists(replay_fp):
        os.remove(replay_fp)


# def on_tb1_text_changed():
#     if os.path.exists(replay_fp):
#         os.remove(replay_fp)


@st.cache_data(show_spinner="使用 Azure 服务评估对话...")
def pronunciation_assessment_func(topic):
    try:
        st.session_state[
            "assessment_tb2"
        ] = pronunciation_assessment_with_content_assessment(
            replay_fp,
            topic,
            language,
            st.secrets["Microsoft"]["SPEECH_KEY"],
            st.secrets["Microsoft"]["SPEECH_REGION"],
        )
    except Exception as e:
        st.toast(e)
        st.stop()


def on_ass_btn_click(topic):
    pronunciation_assessment_func(topic)
    # 显示识别的文本
    st.session_state["text_tb2"] = st.session_state.assessment_tb2["recognized_text"]
    st.session_state["record_ready"] = False


def _get_cn_name(lan):
    for k, v in LAN_MAPS.items():
        if k.startswith(lan):
            return v


def on_ai_btn_click(text_to_be_evaluated_tb1, voice_style, placeholder):
    try:
        get_synthesize_speech(text_to_be_evaluated_tb1, voice_style[0])
    except Exception as e:
        placeholder.error(e)
        st.stop()


# endregion

# region 发音评估


page_emoji = "🗣️"
st.markdown(
    f"""#### {page_emoji} 口语评估
英语口语评估是帮助学习者了解自己的口语水平，并针对性地进行练习的重要工具。本产品基于`Azure`语音服务，借助`Google Vertex AI`，提供口语评估和AI辅助教学功能。

使用方法如下：
1. 请使用👈左侧菜单来设置您的英语水平和要讨论的领域。
2. 基于您的设置，AI将自动生成口语评估话题。您可以使用👇下拉框选择您愿意讨论的话题。
3. 准备就绪后，您可以使用麦克风开始录制关于该主题的讨论，也可以直接上传您已录制好的音频。
4. 点击“评估”按钮，查看发音评估报告。该报告包括发音得分、词汇得分、语法得分和主题得分。
5. 点击“样例”按钮，合成选定的语音风格，生成参考示例。
6. 点击“聆听”按钮，聆听合成语音。
"""
)

# 初始化
if len(st.session_state["tab2_topics"]) == 0:
    st.session_state["tab2_topics"] = generate_english_topics(
        "测试英语口语水平", topic_selectbox, level_selectbox
    )

topic = st.selectbox("话题", st.session_state["tab2_topics"], key="topic_tb2")

st.text_area(
    "📝 **识别的文本**",
    key="text_tb2",
    max_chars=2000,
    height=200,
    label_visibility="collapsed",
    disabled=True,
    # on_change=on_tb1_text_changed,
    placeholder="识别的文本",
    help="识别的文本",
)

message_placeholder = st.empty()
st.info("要求：时长超过15秒，文字篇幅在50个字词和3个句子以上。")
uploaded_file = st.file_uploader("📁 上传音频", type=["wav"], help="上传您录制的音频文件")

btn_num = 8
btn_cols = st.columns(btn_num)


with btn_cols[1]:
    audio = mic_recorder(start_prompt="录音[🔴]", stop_prompt="停止[⏹️]", key="recorder")

rep_btn = btn_cols[2].button(
    "回放[🎧]",
    key="rep_btn_tb1",
    disabled=not st.session_state.get("record_ready", False),
    help="点击按钮，播放麦克风录音或您上传的音频文件。",
)
ass_btn = btn_cols[3].button(
    "评估[🔍]",
    key="ass_btn_tb1",
    help="生成口语评估报告。",
    on_click=on_ass_btn_click,
    args=(topic,),
)
syn_btn = btn_cols[4].button(
    "样例[🤖]",
    key="syn_btn_tb1",
    on_click=on_ai_btn_click,
    help="点击按钮后，AI将生成示例文本，并根据用户选择的风格合成语音。",
)
lst_btn = btn_cols[5].button("聆听[👂]", key="lst_btn_tab1", help="聆听合成语音。")


if uploaded_file is not None:
    st.session_state["record_ready"] = True
    with open(replay_fp, "wb") as f:
        # To read file as string:
        f.write(uploaded_file.read())

if audio:
    # 保存wav文件
    update_mav(audio)
    st.session_state["record_ready"] = True

if rep_btn:
    if not os.path.exists(replay_fp):
        message_placeholder.warning("抱歉，您尚未录制音频，无法回放。")
        st.stop()
    # 自动播放，不显示控件
    components.html(audio_autoplay_elem(replay_fp, fmt="mav"), height=0)

if lst_btn:
    if not os.path.exists(listen_fp):
        message_placeholder.warning("抱歉，您尚未合成音频，无法聆听。")
        st.stop()
    # 自动播放，不显示控件
    components.html(audio_autoplay_elem(listen_fp), height=0)

st.markdown("#### :trophy: 评估结果")
view_report()

with st.expander("🔊 操作提示..."):
    st.markdown("如何进行发音评估👇")
    record_tip = (
        current_cwd / "resource" / "audio_tip" / "cn-pronunciation-assessment-tip.wav"
    )
    st.audio(str(record_tip), format="audio/wav")

    st.markdown("如何聆听发音示例👇")
    lst_tip = current_cwd / "resource" / "audio_tip" / "cn-synthesis-tip.wav"
    st.audio(str(lst_tip), format="audio/wav")
# endregion
