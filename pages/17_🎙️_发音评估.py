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

from mypylib.db_interface import DbInterface
from mypylib.azure_speech import (
    pronunciation_assessment_from_wavfile,
    synthesize_speech_to_file,
)
from mypylib.azure_translator import language_detect
from mypylib.constants import LAN_MAPS, LANGUAGES
from mypylib.html_constants import STYLE, TIPPY_JS
from mypylib.nivo_charts import gen_radar
from mypylib.st_helper import authenticate_and_configure_services, check_and_force_logout
from mypylib.word_utils import audio_autoplay_elem


# region 认证及初始化

authenticate_and_configure_services()

# endregion

# region 常量

CURRENT_CWD: Path = Path(__file__).parent.parent
VOICES_FP = CURRENT_CWD / "resource" / "voices.json"
audio_dir = CURRENT_CWD / "resource" / "audio_data"

if not os.path.exists(audio_dir):
    os.makedirs(audio_dir, exist_ok=True)

# 使用临时文件
replay_fp = os.path.join(
    audio_dir, f"{st.session_state.user_info['user_id']}-tab1-replay.wav"
)
listen_fp = os.path.join(
    audio_dir, f"{st.session_state.user_info['user_id']}-tab1-listen.wav"
)


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

# endregion

# endregion

# region 会话状态

if "assessment_tb1" not in st.session_state:
    st.session_state["assessment_tb1"] = {}

# endregion

# region 函数


@st.cache_data(show_spinner="从 Azure 语音库合成语音...")
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


def generate_word_tooltip(word: dict) -> str:
    """
    生成单词的工具提示。

    Args:
        word (str): 单词的字符串。
        definition (str): 单词的定义字符串。

    Returns:
        tooltip (str): 包含单词和定义的HTML工具提示字符串。
    """
    res = ""
    assert len(word["phonemes"]) == len(word["scores"])
    n = len(word["phonemes"])
    word_score = f"{word['word']} : {int(word['accuracy_score'])}"
    phoneme_cols = """ """.join([f"""<td>{p}&nbsp;</td>""" for p in word["phonemes"]])
    score_cols = """ """.join([f"""<td>{int(s)}&nbsp;</td>""" for s in word["scores"]])
    res = WORD_TOOLTIP_TEMPLATE.format(
        n=n, word_score=word_score, phoneme_cols=phoneme_cols, score_cols=score_cols
    )
    return res


# region 标头

MD_BADGE_MAPS = OrderedDict(
    {
        "None": ("green", "发音优秀", "发音优秀的字词", "success"),
        "Mispronunciation": ("orange", "发音错误", "说得不正确的字词", "warning"),
        "Omission": ("grey", "遗漏字词", "脚本中已提供，但未说出的字词", "secondary"),
        "Insertion": ("red", "插入内容", "不在脚本中但在录制中检测到的字词", "danger"),
        "UnexpectedBreak": ("violet", "意外中断", "同一句子中的单词之间未正确暂停", "info"),
        "MissingBreak": ("blue", "缺少停顿", "当两个单词之间存在标点符号时，词之间缺少暂停", "light"),
        "Monotone": ("rainbow", "单调发音", "这些单词正以平淡且不兴奋的语调阅读，没有任何节奏或表达", "dark"),
    }
)


def view_md_badges():
    assessment = st.session_state["assessment_tb1"]
    cols = st.columns(len(MD_BADGE_MAPS.keys()))
    error_counts = assessment.get("error_counts", {})
    for i, t in enumerate(MD_BADGE_MAPS.keys()):
        num = f"{error_counts.get(t,0):3d}"
        body = f"""{MD_BADGE_MAPS[t][1]}({num})"""
        cols[i].markdown(
            f""":{MD_BADGE_MAPS[t][0]}[{body}]""",
            help=f"✨ {MD_BADGE_MAPS[t][2]}",
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
            return f"""<span class="text-decoration-wavy-underline">[{text}]</span>"""
        case _:
            return f"""{text}"""


def view_word_pronunciation():
    assessment = st.session_state["assessment_tb1"]
    words_list = assessment.get("words_list", [])
    html = ""
    for word in words_list:
        error_type = word["error_type"]
        # print(error_type)
        btn_class = (
            f"""{MD_BADGE_MAPS[error_type][3]}""" if error_type != "success" else ""
        )
        # st.write(word["word"], error_type)
        label = fmt_word(word["word"], error_type)
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
    # 雷达图
    item_maps_tab1 = {
        "pronunciation_score": "发音总评分",
        "accuracy_score": "准确性评分",
        "completeness_score": "完整性评分",
        "fluency_score": "流畅性评分",
        "prosody_score": "韵律分数",
    }
    data_tb1 = {
        key: st.session_state.assessment_tb1.get(key, 0)
        for key in item_maps_tab1.keys()
    }
    gen_radar(data_tb1, item_maps_tab1, 320)


# endregion

# endregion

# region 发音评估报告


def view_report():
    # 发音评估报告
    view_md_badges()
    st.divider()
    view_word_pronunciation()
    view_radar()


# endregion

# region 页配置

st.set_page_config(
    page_title="发音评估",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="auto",
)


# endregion

# region 边栏

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(sidebar_status)

language: str = st.sidebar.selectbox(
    "选择目标语言", options=LANGUAGES, format_func=lambda x: LAN_MAPS[x]
)  # type: ignore

with open(VOICES_FP, "r", encoding="utf-8") as f:
    names = json.load(f)[language]
voice_style: Any = st.sidebar.selectbox(
    "合成语音风格", names, format_func=lambda x: f"{x[2]}【{x[1]}】"
)

# endregion

# region 事件


def reset_page():
    # get_synthesize_speech.clear()
    st.session_state["assessment_tb1"] = {}
    st.session_state["assessment_text_tb1"] = ""
    if os.path.exists(replay_fp):
        os.remove(replay_fp)
    if os.path.exists(listen_fp):
        os.remove(listen_fp)


def on_text_changed():
    if os.path.exists(replay_fp):
        os.remove(replay_fp)
    if os.path.exists(listen_fp):
        os.remove(listen_fp)


# 允许多次评估，不得缓存
# @st.cache_data(show_spinner="使用 Azure 服务评估对话...")
def pronunciation_assessment_func(text_to_be_evaluated_tb1):
    try:
        assessment = pronunciation_assessment_from_wavfile(
            replay_fp,
            text_to_be_evaluated_tb1,
            language,
            st.secrets["Microsoft"]["SPEECH_KEY"],
            st.secrets["Microsoft"]["SPEECH_REGION"],
        )
        st.session_state["assessment_tb1"] = assessment
    except Exception as e:
        st.toast(e)
        st.stop()


def on_ass_btn_click(text_to_be_evaluated_tb1):
    pronunciation_assessment_func(text_to_be_evaluated_tb1)
    st.session_state["tb1_record_ready"] = False


def _get_cn_name(lan):
    for k, v in LAN_MAPS.items():
        if k.startswith(lan):
            return v


def on_syn_btn_click(text_to_be_evaluated_tb1, voice_style, placeholder):
    lan = language_detect(
        text_to_be_evaluated_tb1,
        st.secrets["Microsoft"]["TRANSLATOR_TEXT_SUBSCRIPTION_KEY"],
        st.secrets["Microsoft"]["TRANSLATOR_TEXT_REGION"],
    )
    # actual='zh-Hans' expected='en-US-JennyMultilingualNeural'
    actual = lan[0]["language"].split("-")[0].lower()
    expected = voice_style[0].split("-")[0].lower()
    if actual != expected:
        e_name = _get_cn_name(expected)
        a_name = _get_cn_name(actual)
        placeholder.warning(
            f'您希望合成"{e_name}"语音，但系统检测到您输入的文本是"{a_name}"。在左侧菜单栏中，点击“口语评估”菜单重新开始。'
        )
        st.stop()
    try:
        get_synthesize_speech(text_to_be_evaluated_tb1, voice_style[0])
    except Exception as e:
        placeholder.error(e)
        st.stop()


# endregion

# region 主页

page_emoji = "🎙️"
st.markdown(
    f"""#### {page_emoji} 发音评估
英语发音评估是帮助学习者了解自己的发音水平，并针对性地进行练习的重要工具。本产品基于`Azure`语音服务，提供发音评估和语音合成功能。

如需详细了解使用方法，请将滚动条滚动到页面底部，查看操作提示。
"""
)

text_to_be_evaluated_tb1 = st.text_area(
    ":memo: **发音评估文本**",
    key="assessment_text_tb1",
    max_chars=1000,
    height=120,
    label_visibility="collapsed",
    on_change=on_text_changed,
    placeholder="请在文本框中输入要评估的文本。请注意，您的文本要与左侧下拉列表中的“目标语言”一致。",
    help="✨ 输入要评估的文本。",
)
message_placeholder = st.empty()
btn_num = 8
btn_cols = st.columns(btn_num)

with btn_cols[1]:
    audio = mic_recorder(start_prompt="录音[🔴]", stop_prompt="停止[⏹️]", key="recorder")

rep_btn = btn_cols[2].button(
    "回放[🎧]",
    key="rep_btn_tb1",
    disabled=not st.session_state.get("tb1_record_ready", False),
    help="✨ 点击按钮，回放麦克风录音。",
)

ass_btn = btn_cols[3].button(
    "评估[:mag:]",
    key="ass_btn_tb1",
    help="✨ 生成发音评估报告。",
    on_click=on_ass_btn_click,
    args=(text_to_be_evaluated_tb1,),
)
syn_btn = btn_cols[4].button(
    "合成[:sound:]",
    key="syn_btn_tb1",
    on_click=on_syn_btn_click,
    args=(text_to_be_evaluated_tb1, voice_style, message_placeholder),
    disabled=len(text_to_be_evaluated_tb1) == 0,
    help="✨ 点击合成按钮，合成选定风格的语音。",
)
lst_btn = btn_cols[5].button("聆听[👂]", key="lst_btn_tab1", help="✨ 聆听合成语音。")
cls_btn = btn_cols[6].button(
    "重置[:arrows_counterclockwise:]",
    key="cls_btn_tb1",
    help="✨ 重置发音评估文本。",
    on_click=reset_page,
)

if audio:
    # 保存wav文件
    update_mav(audio)
    st.session_state["tb1_record_ready"] = True

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
    components.html(audio_autoplay_elem(listen_fp, fmt="mav"), height=0)

st.markdown("#### :trophy: 评估结果")
view_report()

# endregion

# region 操作提示

with st.expander(":sound: 操作提示..."):
    st.markdown(
        f"""
使用方法如下：
1. 在文本框内输入要评估的英语文本。
2. 点击“录音”按钮，大声朗读文本框内文本，开始录音。
3. 说完后，点击“停止”按钮，停止录音。
4. 点击“评估”按钮，查看发音评估报告。报告将包括音素准确性、完整性、流畅性、韵律等方面的评分。
5. 点击“合成”按钮，合成选定风格的语音。只有文本框内有文本时，才激活“合成”按钮。
6. 点击“重置”按钮，重置发音评估文本。
"""
    )
    st.markdown("如何进行发音评估👇")
    record_tip = (
        CURRENT_CWD / "resource" / "audio_tip" / "cn-pronunciation-assessment-tip1.wav"
    )
    st.audio(str(record_tip), format="audio/wav")

    st.markdown("如何聆听发音示例👇")
    lst_tip = (
        CURRENT_CWD / "resource" / "audio_tip" / "cn-pronunciation-assessment-tip2.wav"
    )
    st.audio(str(lst_tip), format="audio/wav")

# endregion
