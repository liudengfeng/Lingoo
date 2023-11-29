import hashlib
import json
import os
import queue
import time
import wave

# from st_circular_progress import CircularProgress
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from streamlit_mic_recorder import mic_recorder

from mypylib.authenticate import Authenticator
from mypylib.azure_speech import (
    pronunciation_assessment_from_wavfile,
    synthesize_speech_to_file,
)
from mypylib.azure_translator import language_detect
from mypylib.constants import LAN_MAPS, LANGUAGES
from mypylib.html_constants import CSS, JS, SCRIPT, STYLE
from mypylib.nivo_charts import gen_radar

# region 常量

email = st.experimental_user.email if st.experimental_user.email else "none"
hash_object = hashlib.sha256(email.encode())  # type: ignore
hex_dig = hash_object.hexdigest()[:16]
user_eh = f"h{hex_dig}"

current_cwd: Path = Path(__file__).parent.parent
voices_fp = current_cwd / "static/voices.json"
audio_dir = current_cwd / "audio_data"
if not os.path.exists(audio_dir):
    os.makedirs(audio_dir, exist_ok=True)

# 使用临时文件
replay_fp = os.path.join(audio_dir, f"{user_eh}-replay.wav")
listen_fp = os.path.join(audio_dir, f"{user_eh}-listen.wav")

BADGE_MAPS = OrderedDict(
    {
        "None": ("none", "primary", "发音优秀", "发音优秀的字词"),
        "Mispronunciation": ("misp", "primary", "发音错误", "说得不正确的字词"),
        "Omission": ("omis", "primary", "遗漏", "脚本中提供的但未说出的字词"),
        "Insertion": ("inse", "primary", "插入内容", "不在脚本中但在录制中检测到的字词"),
        "UnexpectedBreak": ("inte", "primary", "意外中断", "同一句子中的单词之间未正确暂停"),
        "MissingBreak": ("paus", "primary", "缺少停顿", "当两个单词之间存在标点符号时，词之间缺少暂停"),
        "Monotone": ("dull", "primary", "单调", "这些单词正以平淡且不兴奋的语调阅读，没有任何节奏或表达"),
    }
)

WORD_TOOLTIP_TEMPLATE = """
<table>
    <tr>
        <td colspan="{n}">{word_score}</td>
    </tr>
    <tr>
        {phoneme_cols}
    </tr>
    <tr>
        {score_cols}
    </tr>
</table>
"""

BADGE_TEMPLATE = """
<button type="button" class="btn btn-{btn_class}" data-bs-toggle="tooltip" data-bs-placement="top"
        data-bs-custom-class="custom-tooltip"
        data-bs-title="{title}">
  {label} <span class="badge text-bg-{color}">{num}</span>
</button>
"""

BTN_TEMPLATE = """
<button type="button" class="btn {btn_class}"
        data-tippy-content="{title}">
  {label}
</button>
"""


recording_queue = queue.Queue()
rec_status = ""

# endregion

# region 会话状态

if "assessment_tb1" not in st.session_state:
    st.session_state["assessment_tb1"] = {}

if "assessment_tb2" not in st.session_state:
    st.session_state["assessment_tb2"] = {}

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

if "auth" not in st.session_state:
    st.session_state["auth"] = Authenticator()

# endregion

# region 函数


# @st.cache_data(show_spinner="从 Azure 语音库合成语音...")
def get_synthesize_speech(text, voice):
    synthesize_speech_to_file(
        text,
        listen_fp,
        # language,
        st.secrets["Microsoft"]["SPEECH_KEY"],
        st.secrets["Microsoft"]["SPEECH_SERVICE_REGION"],
        voice,
    )


# TODO:在会话中保存音频数据
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
    <div style="width: 12px; height: 12px; background-color: #c02a2a; margin-right: 5px; margin-left: 5px;"></div>\
    <span>0 ~ 59</span>\
    <div style="width: 12px; height: 12px; background-color: yellow; margin-right: 5px;margin-left: 5px;"></div>\
    <span>60 ~ 79</span>\
    <div style="width: 12px; height: 12px; background-color: green; margin-right: 5px;margin-left: 5px;"></div>\
    <span>80 ~ 100</span>\
</div>\
"""


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


def generate_badges(assessment):
    """
    Generates a list of badges based on the error counts in the given assessment.

    Args:
        assessment (dict): A dictionary containing error counts for different types of errors.

    Returns:
        list: A list of HTML badge strings, each representing a type of error and its count.
    """
    badges = []
    error_counts = assessment.get("error_counts", {})
    for t in BADGE_MAPS.keys():
        if t in error_counts.keys():
            badges.append(
                BADGE_TEMPLATE.format(
                    btn_class=BADGE_MAPS[t][0],
                    color=BADGE_MAPS[t][1],
                    label=BADGE_MAPS[t][2],
                    title=BADGE_MAPS[t][3],
                    num=error_counts[t],
                )
            )
    return badges


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
        case _:
            return f"""{text}"""


def generate_paragraph(assessment):
    # 发音评估单词级报告文本【提示信息展示音素得分】
    words_list = assessment.get("words_list", [])
    res = ""
    for word in words_list:
        error_type = word["error_type"]
        # print(error_type)
        btn_class = (
            f"""btn-{BADGE_MAPS[error_type][0]}""" if error_type != "None" else ""
        )
        label = fmt_word(word["word"], error_type)
        # 解决单引号、双引号问题
        title = generate_word_tooltip(word).replace("'", "&#39;").replace('"', "&quot;")
        res += BTN_TEMPLATE.format(
            btn_class=btn_class,
            title=title,
            label=label,
        )
    return f"""<p class="text-start">{res}</p>"""


def view_progress(value: int):
    """
    Displays a progress bar with the given value.

    Parameters:
    value (int): The value to display in the progress bar.

    Returns:
    None
    """
    color = get_bg_color(value)
    html = f"""\
<div class="progress" role="progressbar" aria-label="Success example" aria-valuenow="{value}" aria-valuemin="0"\
    aria-valuemax="100">\
    <div class="progress-bar {color}" style="width: {value}%">{value}%</div>\
</div>\
    """
    components.html(CSS + JS + STYLE + html, height=30)


def view_report_tb1(assessment_placeholder, add_spinner=False):
    name = "assessment_{}".format(st.session_state["tab_flag"])
    assessment = st.session_state[name]
    badges = generate_badges(assessment)
    html = "".join(badges)
    html += generate_paragraph(assessment)
    if len(badges) > 0:
        html = "<hr>" + html + "<hr>"
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

    with assessment_placeholder:
        components.html(CSS + JS + STYLE + html + SCRIPT, height=200, scrolling=True)
        gen_radar(data_tb1, item_maps_tab1, 320)


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
    if add_spinner:
        score_legend += "<hr>"
    components.html(CSS + JS + STYLE + score_legend + SCRIPT)


# endregion

# region 页配置

st.set_page_config(
    page_title="评估发音与对话",
    page_icon="🗣️",
    layout="wide",
    initial_sidebar_state="auto",
)

if not st.session_state.auth.is_service_active(st.session_state["user_id"]):
    st.error("您尚未付费，无法使用此功能。")
    st.stop()

tab1, tab2 = st.tabs(["🎙️ 发音评估", "🗣️ 对话能力"])
# endregion

# region 边栏

language: str = st.sidebar.selectbox(
    "选择目标语言", options=LANGUAGES, format_func=lambda x: LAN_MAPS[x.lower().split("-")[0]]
)  # type: ignore

with open(voices_fp, "r", encoding="utf-8") as f:
    names = json.load(f)[language]
voice_style: Any = st.sidebar.selectbox(
    "合成语音风格", names, format_func=lambda x: f"{x[2]}【{x[1]}】"
)

# endregion


# region 事件


def reset_tb1():
    # get_synthesize_speech.clear()
    st.session_state["assessment_tb1"] = {}
    st.session_state["text_tb1"] = ""
    if os.path.exists(replay_fp):
        os.remove(replay_fp)
    if os.path.exists(listen_fp):
        os.remove(listen_fp)


def on_tb1_text_changed():
    if os.path.exists(replay_fp):
        os.remove(replay_fp)
    if os.path.exists(listen_fp):
        os.remove(listen_fp)


def on_cls_btn_click_tb2():
    st.session_state["assessment_tb2"] = {}
    st.session_state["text_to_be_evaluated_tb2"] = ""
    # st.session_state["report_ready"] = False
    st.session_state["record_ready"] = False
    if os.path.exists(replay_fp):
        os.remove(replay_fp)


def fpronunciation_assessmentunc(text_to_be_evaluated_tb1, status_placeholder):
    st.toast("正在评估对话...", icon="💯")
    status_placeholder.info("💯 正在评估对话...")
    try:
        assessment = pronunciation_assessment_from_wavfile(
            replay_fp,
            text_to_be_evaluated_tb1,
            language,
            st.secrets["Microsoft"]["SPEECH_KEY"],
            st.secrets["Microsoft"]["SPEECH_SERVICE_REGION"],
        )
        st.session_state["assessment_tb1"] = assessment
        status_placeholder.info("🎈 完成评估")
    except Exception as e:
        status_placeholder.error(e)
        st.stop()


def on_ass_btn_tb1_click(text_to_be_evaluated_tb1, status_placeholder):
    fpronunciation_assessmentunc(text_to_be_evaluated_tb1, status_placeholder)
    st.session_state["record_ready"] = False


def on_syn_btn_tb1_click(text_to_be_evaluated_tb1, voice_style, status_placeholder):
    lan = language_detect(
        text_to_be_evaluated_tb1,
        st.secrets["Microsoft"]["TRANSLATOR_TEXT_SUBSCRIPTION_KEY"],
        st.secrets["Microsoft"]["TRANSLATOR_TEXT_REGION"],
    )
    actual = lan[0]["language"].split("-")[0].lower()
    expected = voice_style[0].split("-")[0].lower()
    if actual != expected:
        status_placeholder.warning(
            f'您希望合成"{LAN_MAPS[expected]}"语音，但系统检测到您输入的文本是"{LAN_MAPS[actual]}"。'
        )
        st.stop()
    try:
        get_synthesize_speech(text_to_be_evaluated_tb1, voice_style[0])
    except Exception as e:
        status_placeholder.error(e)
        st.stop()


# endregion

# region 发音评估


with tab1:
    st.session_state["tab_flag"] = "tb1"
    page_emoji = "🎙️"
    st.markdown(
        f"""#### {page_emoji} 发音评估
- 输入要评估的文本
- 光标移出文本区域后，激活语音"合成"按钮
"""
    )

    text_to_be_evaluated_tb1 = st.text_area(
        "📝 **发音评估文本**",
        key="text_tb1",
        max_chars=1000,
        height=120,
        label_visibility="collapsed",
        on_change=on_tb1_text_changed,
        # help="输入要评估的文本。光标移出文本区域后，激活录音按钮。",
    )
    status_placeholder = st.empty()
    btn_num = 6
    btn_cols = st.columns(btn_num)
    audio_cols = st.columns([1, 2, 1, 1, 2, 1])

    with btn_cols[1]:
        audio = mic_recorder(start_prompt="录音[🔴]", stop_prompt="停止[⏹️]", key="recorder")

    ass_btn = btn_cols[2].button(
        "评估[🔍]",
        key="ass_btn_tb1",
        help="生成发音评估报告",
        on_click=on_ass_btn_tb1_click,
        args=(text_to_be_evaluated_tb1, status_placeholder),
    )
    syn_btn = btn_cols[3].button(
        "合成[🔊]",
        key="syn_btn_tb1",
        on_click=on_syn_btn_tb1_click,
        args=(text_to_be_evaluated_tb1, voice_style, status_placeholder),
        disabled=len(text_to_be_evaluated_tb1) == 0,
        help="点击合成按钮，合成选定风格的语音。只有文本或语音风格变化后，才从 Azure 语音库合成语音。",
    )
    cls_btn = btn_cols[4].button(
        "重置[🔄]",
        key="cls_btn_tb1",
        help="重置发音评估文本",
        on_click=reset_tb1,
    )

    # 回放录音
    audio_cols[0].markdown("录音👉")
    replay_placeholder = audio_cols[1].empty()

    if audio:
        # 保存wav文件
        update_mav(audio)
        st.session_state["record_ready"] = True

    if os.path.exists(replay_fp):
        replay_placeholder.audio(replay_fp)

    # 合成
    audio_cols[3].markdown("合成👉")
    listen_placeholder = audio_cols[4].empty()
    if os.path.exists(listen_fp):
        listen_placeholder.audio(listen_fp, format="audio/wav")

    st.markdown("#### :trophy: 评估结果")

    assessment_placeholder = st.container()
    view_report_tb1(assessment_placeholder)

    progress_cols = st.columns(5)

    view_score_legend(progress_cols, True)

    with st.expander("操作提示..."):
        # 录音提示
        st.markdown("录音提示👇")
        record_tip = current_cwd / "static" / "audio" / "cn-record-tip.wav"
        st.audio(str(record_tip), format="audio/wav")

        st.markdown("合成提示👇")
        lst_tip = current_cwd / "static" / "audio" / "cn-synthesis-tip.wav"
        st.audio(str(lst_tip), format="audio/wav")
# endregion

# region 对话能力

with tab2:
    st.error("尚未完成")
    st.stop()
    st.session_state["tab_flag"] = "tb2"
    page_emoji = "🗣️"
    st.markdown(f"#### {page_emoji} 对话能力")

    st.markdown("📝 **要讨论的主题**", help="输入要讨论的主题。光标移出文本区域后，激活录音按钮。")
    text_to_be_evaluated_tb2 = st.text_area(
        "📝 **主题文本**",
        key="text_to_be_evaluated_tb2",
        max_chars=100,
        height=30,
        label_visibility="collapsed",
        # on_change=on_tb2_text_changed,
        # help="输入要评估的文本。光标移出文本区域后，激活录音按钮。",
    )

    btn_num = 6
    btn_cols = st.columns(btn_num)
    rec_btn = btn_cols[1].button(
        "录音[🎙️]",
        key="rec_btn_tb2",
        # on_click=on_record_btn_click,
        disabled=not st.session_state.get("record_ready", False)
        or len(text_to_be_evaluated_tb2) == 0,
        help="按麦克风开始说话。要求录制不少于15秒的语音，单词不少于50个，句子不少于3个。",
    )
    stop_rec_btn = btn_cols[2].button(
        "停止[⏹️]",
        key="stop_rec_btn_tb2",
        disabled=not st.session_state.get("recording", False),
        # on_click=on_stop_btn_click,
        help="停止麦克风录音，显示发音评估结果",
    )
    cls_btn = btn_cols[4].button(
        "重置[🔄]",
        key="cls_btn_tb2",
        help="重置发音评估文本",
        on_click=on_cls_btn_click_tb2,
    )

    status_placeholder = st.empty()

    audio_col_1, audio_col_2 = st.columns(2)

    # 回放
    audio_col_1.markdown("🎙️ 👇回放录音", help="点击下方按钮，回放麦克风录音")
    replay_placeholder = audio_col_1.empty()
    if not os.path.exists(replay_fp):
        record_tip = current_cwd / "static" / "audio" / "cn_replay.wav"
        replay_placeholder.audio(str(record_tip), format="audio/wav")
    else:
        replay_placeholder.audio(replay_fp, format="audio/wav")

    st.markdown("#### 评估结果")

    assessment_placeholder = st.container()

    # with assessment_placeholder:
    #     view_report(True)

    progress_cols = st.columns(4)

    # cp1 = CircularProgress(
    #     label="发音评分",
    #     value=int(st.session_state.assessment_tb2.get("pronunciation_score", 0)),
    #     size="Medium",
    #     color=get_cp_color(
    #         int(st.session_state.assessment_tb2.get("pronunciation_score", 0))
    #     ),
    #     key=f"dsh_pronunciation_score_tb2",
    # )
    # cp2 = CircularProgress(
    #     label="内容分数",
    #     value=int(st.session_state.assessment_tb2.get("content_score", 0)),
    #     size="Medium",
    #     color=get_cp_color(
    #         int(st.session_state.assessment_tb2.get("content_score", 0))
    #     ),
    #     key=f"dsh_content_score_tb2",
    # )

    with progress_cols[0]:
        st.markdown(
            "**:trophy:发音分数**",
            help="表示给定语音发音质量的总体分数。它是从 AccuracyScore、FluencyScore、CompletenessScore、Weight 按权重聚合的。",
        )
        # cp1.st_circular_progress()
        view_score_legend(True)

    with progress_cols[1]:
        st.markdown("**得分明细**")
        st.markdown(
            "准确性评分",
            help="语音的发音准确性。准确性表示音素与母语说话人的发音的匹配程度。字词和全文的准确性得分是由音素级的准确度得分汇总而来。",
        )
        view_progress(int(st.session_state.assessment_tb2.get("accuracy_score", 0)))
        st.markdown(
            "流畅性评分",
            help="给定语音的流畅性。流畅性表示语音与母语说话人在单词间的停顿上有多接近。",
        )
        view_progress(int(st.session_state.assessment_tb2.get("fluency_score", 0)))
        st.markdown(
            "韵律分数",
            help="给定语音的韵律。韵律指示给定语音的性质，包括重音、语调、语速和节奏。",
        )
        view_progress(int(st.session_state.assessment_tb2.get("prosody_score", 0)))

    with progress_cols[2]:
        st.markdown(
            "**:trophy:内容分数**",
            help="此分数提供语音内容的聚合评估，包括词汇分数、语法分数和主题分数。",
        )
        # cp2.st_circular_progress()
        view_score_legend(True)

    with progress_cols[3]:
        st.markdown("**得分明细**")
        st.markdown(
            "词汇分数",
            help="词汇运用能力的熟练程度是通过说话者有效地使用单词来评估的，即在特定语境中使用某单词以表达观点是否恰当。",
        )
        view_progress(int(st.session_state.assessment_tb2.get("accuracy_score", 0)))
        st.markdown(
            "语法分数",
            help="词汇运用能力的熟练程度是通过说话者有效地使用单词来评估的，即在特定语境中使用某单词以表达观点是否恰当。",
        )
        view_progress(int(st.session_state.assessment_tb2.get("fluency_score", 0)))
        st.markdown(
            "主题分数",
            help="词汇运用能力的熟练程度是通过说话者有效地使用单词来评估的，即在特定语境中使用某单词以表达观点是否恰当。",
        )
        view_progress(int(st.session_state.assessment_tb2.get("prosody_score", 0)))
# endregion
