import json
import logging
import os
import random
import re
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from mypylib.google_api import (
    generate_word_memory_tip,
    generate_word_test,
    get_translation_client,
    google_translate,
)
from mypylib.st_helper import authenticate, check_and_force_logout
from mypylib.word_utils import (
    audio_autoplay_elem,
    get_or_create_and_return_audio_data,
    remove_trailing_punctuation,
)

# 创建或获取logger对象
logger = logging.getLogger("streamlit")

# region 页设置

st.set_page_config(
    page_title="记忆单词",
    page_icon=":books:",
    layout="wide",
)


# endregion

# region 常量
# streamlit中各页都是相对当前根目录

CURRENT_CWD: Path = Path(__file__).parent.parent
DICT_DIR = CURRENT_CWD / "resource/dictionary"

# endregion

# region 认证及初始化

authenticate(st)

if "current_tab" not in st.session_state:
    st.session_state["current_tab"] = "Default Tab"


@st.cache_resource  # 👈 Add the caching decorator
def load_word_dict():
    with open(
        DICT_DIR / "word_lists_by_edition_grade.json", "r", encoding="utf-8"
    ) as f:
        return json.load(f)


if len(st.session_state.get("word_dict", {})) == 0:
    st.session_state["word_dict"] = load_word_dict()

# endregion


# region 闪卡状态

if "flashcard_words" not in st.session_state:
    st.session_state["flashcard_words"] = []

if "flashcard_word_info" not in st.session_state:
    st.session_state["flashcard_word_info"] = {}

if "flashcard_display_state" not in st.session_state:
    st.session_state["flashcard_display_state"] = "全部"

# 初始化单词的索引
if "current_flashcard_word_index" not in st.session_state:
    st.session_state["current_flashcard_word_index"] = -1

# endregion

# region 事件及函数


def generate_flashcard_words():
    # 获取选中的单词列表
    word_lib_name = st.session_state["selected_list"]
    words = st.session_state.word_dict[word_lib_name]
    num_words = st.session_state["num_words_key"]
    n = min(num_words, len(words))
    # 随机选择单词
    st.session_state.flashcard_words = random.sample(words, n)
    st.toast(
        f"当前单词列表名称：{word_lib_name} 闪卡单词数量: {len(st.session_state.flashcard_words)}"
    )


@st.cache_data(ttl=timedelta(hours=24), max_entries=10000, show_spinner="获取单词信息...")
def get_word_info(word):
    return st.session_state.dbi.find_word(word)


# endregion

# region 侧边栏


# 从集合中提取个人词库，添加到word_lists中
if st.session_state["user_info"] is not None:
    personal_word_list = st.session_state.dbi.find_personal_dictionary(
        st.session_state["user_info"]
    )
    if len(personal_word_list) > 0:
        st.session_state.word_dict["0-个人词库"] = personal_word_list

with open(CURRENT_CWD / "resource/voices.json", "r", encoding="utf-8") as f:
    voice_style_options = json.load(f)

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(st, sidebar_status)

# 让用户选择语音风格
pronunciation = st.sidebar.radio("请选择发音标准", ("美式", "英式"))
style = "en-US" if pronunciation == "美式" else "en-GB"

# 固定语音风格
voice_style = voice_style_options[style][0]
st.sidebar.info(f"语音风格：{voice_style[0]}({voice_style[1]})")

# 在侧边栏添加一个选项卡让用户选择一个单词列表
st.sidebar.selectbox(
    "请选择单词列表",
    sorted(list(st.session_state.word_dict.keys())),
    key="selected_list",
    on_change=generate_flashcard_words,
    format_func=lambda x: x.split("-", maxsplit=1)[1],
)


# 在侧边栏添加一个滑块让用户选择记忆的单词数量

st.sidebar.slider(
    "请选择计划记忆的单词数量",
    10,
    50,
    step=5,
    key="num_words_key",
)

# endregion

# region tabs
# 将二者分离，避免格式经常被重置
tab_names = ["记忆闪卡", "单词拼图", "图片测词", "单词测验", "个人词库", "个人统计"]
tab_emoji = [
    ":book:",
    ":jigsaw:",
    ":frame_with_picture:",
    ":memo:",
    ":books:",
    ":bar_chart:",
]
tab_items = [e + " " + n for e, n in zip(tab_emoji, tab_names)]
tabs = st.tabs(tab_items)
# endregion

# region 记忆闪卡辅助


def on_prev_btn_click():
    st.session_state["current_flashcard_word_index"] -= 1


def on_next_btn_click():
    st.session_state["current_flashcard_word_index"] += 1


template = """
##### 单词或短语：:rainbow[{word}]
- CEFR最低分级：:green[{cefr}]
- 翻译：{translation}
- 美式音标：:blue[{us_written}]  
- 英式音标：:violet[{uk_written}]
"""


def _rainbow_word(example: str, word: str):
    pattern = r"\b" + word + r"\b"
    match = re.search(pattern, example)
    if match:
        return re.sub(pattern, f":rainbow[{word}]", example)
    pattern = r"\b" + word.capitalize() + r"\b"
    match = re.search(pattern, example)
    if match:
        return re.sub(pattern, f":rainbow[{word.capitalize()}]", example)
    return example


def _view_detail(container, detail, t_detail, word):
    d1 = remove_trailing_punctuation(detail["definition"])
    d2 = remove_trailing_punctuation(t_detail["definition"])
    e1 = detail["examples"]
    e2 = t_detail["examples"]
    num_elements = min(3, len(e1))
    # 随机选择元素
    content = ""
    indices = random.sample(range(len(e1)), num_elements)
    if st.session_state.flashcard_display_state == "全部":
        container.markdown(f"**:blue[definition：{d1}]**")
        container.markdown(f"**:violet[定义：{d2}]**")
        for i in indices:
            content += f"- {_rainbow_word(e1[i], word)}\n"
            content += f"- {e2[i]}\n"
    elif st.session_state.flashcard_display_state == "英文":
        container.markdown(f"**:blue[definition：{d1}]**")
        for i in indices:
            content += f"- {_rainbow_word(e1[i], word)}\n"
    else:
        # 只显示译文
        container.markdown(f"**:violet[定义：{d2}]**")
        for i in indices:
            content += f"- {e2[i]}\n"
    container.markdown(content)


def _view_pos(container, key, en, zh, word):
    container.markdown(f"**{key}**")
    for i in range(len(en)):
        _view_detail(container, en[i], zh[i], word)


def view_pos(container, word_info, word):
    en = word_info.get("en-US", {})
    zh = word_info.get("zh-CN", {})
    for key in en.keys():
        container.divider()
        _view_pos(container, key, en[key], zh[key], word)


@st.cache_data(ttl=timedelta(hours=12), max_entries=1000, show_spinner="获取 Ai 提示...")
def _memory_tip(word):
    return generate_word_memory_tip(word)


@st.cache_data(ttl=timedelta(hours=12), max_entries=1000, show_spinner="获取音频元素...")
def get_audio_html(word, voice_style):
    """
    获取单词的音频HTML代码，可供浏览器内自动播放。

    参数：
    - word：要获取音频的单词（字符串）
    - voice_style：音频风格（字符串）

    返回值：
    - 音频的HTML代码（字符串）
    """
    audio_data = get_or_create_and_return_audio_data(word, voice_style[0], st.secrets)
    return audio_autoplay_elem(audio_data)


def view_flash_word(container, tip_placeholder):
    """
    Display the flashcard word and its information.

    Args:
        container (object): The container to display the flashcard word and information.
        tip_placeholder (object): The placeholder to display the memory tip.

    Returns:
        None
    """

    if st.session_state.current_flashcard_word_index == -1:
        return

    word = st.session_state.flashcard_words[
        st.session_state.current_flashcard_word_index
    ]
    if word not in st.session_state.flashcard_word_info:
        st.session_state.flashcard_word_info[word] = get_word_info(word)

    word_info = st.session_state.flashcard_word_info.get(word, {})
    if not word_info:
        st.error(f"没有该单词：“{word}”的信息。TODO：添加到单词库。")
        st.stop()

    if st.secrets.get("dev", "") in ["streamlit", "azure"]:
        with tip_placeholder.expander("记忆提示"):
            # 生成记忆提示
            memory_tip = _memory_tip(word)
            st.markdown(memory_tip)

    v_word = word
    t_word = ""
    if st.session_state.flashcard_display_state == "中文":
        v_word = ""

    if st.session_state.flashcard_display_state != "英文":
        t_word = word_info["zh-CN"].get("translation", "")

    md = template.format(
        word=v_word,
        cefr=word_info.get("level", ""),
        us_written=word_info.get("us_written", ""),
        uk_written=word_info.get("uk_written", ""),
        translation=t_word,
    )

    container.divider()
    container.markdown(md)

    view_pos(container, word_info, word)


# endregion

# region 记忆闪卡

with tabs[tab_items.index(":book: 记忆闪卡")]:
    st.session_state["current_tab"] = "记忆闪卡"
    btn_cols = st.columns(9)
    tip_placeholder = st.empty()
    container = st.container()

    # placeholder = st.container()
    # 创建前后选择的按钮
    display_status_button = btn_cols[1].button(
        ":recycle:",
        key="mask",
        help="点击按钮，可切换显示状态。初始状态显示中英对照。点击按钮，切换为只显示英文。再次点击按钮，切换为只显示中文。",
    )
    prev_btn = btn_cols[2].button(
        ":leftwards_arrow_with_hook:",
        key="prev",
        help="点击按钮，切换到上一个单词。",
        on_click=on_prev_btn_click,
        disabled=st.session_state.current_flashcard_word_index <= 0,
    )
    next_btn = btn_cols[3].button(
        ":arrow_right_hook:",
        key="next",
        help="点击按钮，切换到下一个单词。",
        on_click=on_next_btn_click,
        disabled=len(st.session_state.flashcard_words)
        and st.session_state.current_flashcard_word_index
        == len(st.session_state.flashcard_words) - 1,  # type: ignore
    )
    play_btn = btn_cols[4].button(
        ":sound:",
        key="play",
        help="聆听单词发音",
        disabled=st.session_state.current_flashcard_word_index == -1,
    )
    add_btn = btn_cols[5].button(
        ":heavy_plus_sign:",
        key="add",
        help="将当前单词添加到个人词库",
        disabled=st.session_state.current_flashcard_word_index == -1,
    )
    del_btn = btn_cols[6].button(
        ":heavy_minus_sign:",
        key="del",
        help="将当前单词从个人词库中删除",
        disabled=st.session_state.current_flashcard_word_index == -1,
    )
    update_flashcard_wordbank_button = btn_cols[7].button(
        ":arrows_counterclockwise:", key="refresh", help="左侧菜单改变词库或记忆数量后，请重新生成闪卡单词"
    )

    placeholder = st.empty()

    # 创建按钮
    if display_status_button:
        if st.session_state.flashcard_display_state == "全部":
            st.session_state.flashcard_display_state = "英文"
        elif st.session_state.flashcard_display_state == "英文":
            st.session_state.flashcard_display_state = "中文"
        else:
            st.session_state.flashcard_display_state = "全部"

    if play_btn:
        word = st.session_state.flashcard_words[
            st.session_state.current_flashcard_word_index
        ]
        # 使用会话缓存，避免重复请求
        audio_html = get_audio_html(word, voice_style)
        components.html(audio_html)

    if update_flashcard_wordbank_button:
        generate_flashcard_words()
        # 恢复初始显示状态
        st.session_state.flashcard_display_state = "全部"
        st.session_state["current_flashcard_word_index"] = -1

    if add_btn:
        word = st.session_state.flashcard_words[
            st.session_state.current_flashcard_word_index
        ]
        st.session_state.dbi.add_word_to_personal_dictionary(
            st.session_state["user_info"], word
        )
        st.toast(f"已添加单词：{word}到个人词库。")

    if del_btn:
        word = st.session_state.flashcard_words[
            st.session_state.current_flashcard_word_index
        ]
        st.session_state.dbi.remove_word_from_personal_dictionary(
            st.session_state["user_info"], word
        )
        st.toast(f"已从个人词库中删除单词：{word}。")

    # 控制闪卡单词的显示
    if st.session_state["current_tab"] == "记忆闪卡":
        # 初始化闪卡单词
        if len(st.session_state.flashcard_words) == 0:
            generate_flashcard_words()
        view_flash_word(container, tip_placeholder)

# endregion

# region 单词拼图辅助

if "puzzle_idx" not in st.session_state:
    st.session_state["puzzle_idx"] = -1

if "puzzle_words" not in st.session_state:
    st.session_state["puzzle_words"] = []

if "puzzle_answer_value" not in st.session_state:
    st.session_state["puzzle_answer_value"] = ""

if "puzzle_view_word" not in st.session_state:
    st.session_state["puzzle_view_word"] = []

if "clicked_character" not in st.session_state:
    st.session_state["clicked_character"] = []

if "puzzle_test_score" not in st.session_state:
    st.session_state["puzzle_test_score"] = {}


def gen_puzzle_words():
    # 获取选中的单词列表
    words = st.session_state.word_dict[st.session_state["selected_list"]]
    num_words = st.session_state["num_words_key"]
    n = min(num_words, len(words))
    # 随机选择单词
    st.session_state.puzzle_words = random.sample(words, n)


def get_word_definition(word):
    word_info = get_word_info(word)
    definition = ""
    en = word_info.get("en-US", {})
    for k, v in en.items():
        definition += f"\n{k}\n"
        for d in v:
            definition += f'- {d["definition"]}\n'
    return definition


def prepare_puzzle():
    word = st.session_state.puzzle_words[st.session_state.puzzle_idx]
    ws = [w for w in word]
    random.shuffle(ws)
    st.session_state.puzzle_view_word = ws
    st.session_state.clicked_character = [False] * len(ws)
    st.session_state.puzzle_answer_value = ""


def view_puzzle_word():
    if st.session_state.puzzle_idx == -1:
        return

    if len(st.session_state.puzzle_view_word) == 0:
        prepare_puzzle()

    ws = st.session_state["puzzle_view_word"]
    n = len(ws)
    cols = st.columns(n + 8)
    button_placeholders = [cols[i].empty() for i in range(n)]
    for i in range(n):
        if button_placeholders[i].button(
            ws[i],
            key=f"btn_{i}",
            disabled=st.session_state.clicked_character[i],
            help="点击按钮，选择单词拼图中的字母。",
            type="primary",
        ):
            st.session_state.puzzle_answer_value += ws[i]
            st.session_state.clicked_character[i] = True
            st.rerun()


def display_puzzle_hint(puzzle_progress):
    if st.session_state.puzzle_idx == -1:
        return
    n = len(st.session_state.puzzle_words)
    progress = 1.0 * (st.session_state.puzzle_idx + 1) / n
    # st.write("进度：", progress, "idx", st.session_state.puzzle_idx)
    puzzle_progress.progress(progress, text=":jigsaw: 单词拼图进度")
    word = st.session_state.puzzle_words[st.session_state.puzzle_idx]
    definition = get_word_definition(word)
    st.write("提示信息：")
    st.markdown(definition)


def on_prev_puzzle_btn_click():
    st.session_state["puzzle_idx"] -= 1
    st.session_state.puzzle_answer_value = ""


def on_next_puzzle_btn_click():
    st.session_state["puzzle_idx"] += 1
    st.session_state.puzzle_answer_value = ""


# endregion

# region 单词拼图

with tabs[tab_items.index(":jigsaw: 单词拼图")]:
    st.session_state["current_tab"] = "单词拼图"
    st.markdown(
        "单词拼图是一种记忆单词的游戏，其玩法是将一些字母打乱，玩家需要根据这些字母，结合提示信息拼出正确的单词。它是一种非常有效的学习方式，可以帮助我们提高词汇量、拼写能力、思维能力和解决问题能力。单词来自于您的记忆闪卡。参考：[Cambridge Dictionary](https://dictionary.cambridge.org/)"
    )
    puzzle_progress = st.empty()
    puzzle_cols = st.columns(4)
    prev_puzzle_btn = puzzle_cols[1].button(
        ":leftwards_arrow_with_hook:",
        key="prev-puzzle",
        help="点击按钮，切换到上一单词拼图。",
        on_click=on_prev_puzzle_btn_click,
        disabled=st.session_state.puzzle_idx <= 0,
    )
    next_puzzle_btn = puzzle_cols[2].button(
        ":arrow_right_hook:",
        key="next-puzzle",
        help="点击按钮，切换到下一单词拼图。",
        on_click=on_next_puzzle_btn_click,
        disabled=st.session_state.puzzle_idx == st.session_state["num_words_key"] - 1,
    )

    update_puzzle_wordbank_button = puzzle_cols[3].button(
        ":arrows_counterclockwise:", key="refresh-puzzle", help="重新生成单词列表"
    )

    if prev_puzzle_btn:
        prepare_puzzle()

    if next_puzzle_btn:
        prepare_puzzle()

    if update_puzzle_wordbank_button:
        gen_puzzle_words()
        # 恢复初始显示状态
        st.session_state.puzzle_idx = -1
        st.session_state["puzzle_view_word"] = []
        st.session_state["puzzle_test_score"] = {}
        st.session_state.puzzle_answer_value = ""

    if st.session_state.current_tab == "单词拼图":
        if len(st.session_state.puzzle_words) == 0:
            gen_puzzle_words()

        display_puzzle_hint(puzzle_progress)
        view_puzzle_word()

        if st.session_state.puzzle_idx != -1:
            user_input = st.text_input(
                "点击字符按钮或输入您的答案",
                placeholder="点击字符按钮或直接输入您的答案",
                value=st.session_state.puzzle_answer_value,
                key="puzzle_answer",
                label_visibility="collapsed",
            )
            puzzle_score = st.empty()
            sumbit_cols = st.columns(6)

            if sumbit_cols[0].button("重试", help="恢复初始状态，重新开始。"):
                prepare_puzzle()
                st.rerun()

            if sumbit_cols[1].button("检查", help="点击按钮，检查您的答案是否正确。"):
                word = st.session_state.puzzle_words[st.session_state.puzzle_idx]
                if word not in st.session_state.flashcard_word_info:
                    st.session_state.flashcard_word_info[word] = get_word_info(word)

                msg = f'单词：{word}\t翻译：{st.session_state.flashcard_word_info[word]["zh-CN"]["translation"]}'
                if user_input == word:
                    st.balloons()
                    st.session_state.puzzle_test_score[word] = True
                else:
                    st.write(f"对不起，您回答错误。正确的单词应该为：{word}")
                    st.session_state.puzzle_test_score[word] = False

                # if st.session_state.puzzle_idx == st.session_state["num_words_key"] - 1:
                score = (
                    sum(st.session_state.puzzle_test_score.values())
                    / st.session_state["num_words_key"]
                    * 100
                )
                msg = f":red[您的得分：{score:.0f}%]\t{msg}"
                puzzle_score.markdown(msg)


# endregion

# region 图片测词辅助

if "pic_idx" not in st.session_state:
    st.session_state["pic_idx"] = -1


if "pic_tests" not in st.session_state:
    st.session_state["pic_tests"] = []

if "user_pic_answer" not in st.session_state:
    st.session_state["user_pic_answer"] = {}


def on_prev_pic_btn_click():
    st.session_state["pic_idx"] -= 1


def on_next_pic_btn_click():
    st.session_state["pic_idx"] += 1


pic_dir = CURRENT_CWD / "resource/quiz/images"
pic_categories = sorted([d.name for d in pic_dir.iterdir() if d.is_dir()])


def gen_pic_tests(category, num):
    pic_qa_path = CURRENT_CWD / "resource/quiz/quiz_image_qa.json"
    pic_qa = {}
    with open(pic_qa_path, "r", encoding="utf-8") as f:
        pic_qa = json.load(f)
    qa_filtered = [v for v in pic_qa if v["category"].startswith(category)]
    random.shuffle(qa_filtered)
    # 重置
    data = qa_filtered[:num]
    for d in data:
        random.shuffle(d["options"])
    st.session_state["pic_tests"] = data


def on_pic_radio_change(idx):
    # 保存用户答案
    st.session_state.user_pic_answer[idx] = st.session_state["pic_options"]


def view_pic_question(container):
    if st.session_state.pic_idx == -1:
        return
    # progress_text = "答题进度"
    tests = st.session_state.pic_tests
    n = len(tests)
    idx = st.session_state.pic_idx

    question = tests[idx]["question"]
    o_options = tests[idx]["options"]
    options = []
    for f, o in zip("ABC", o_options):
        options.append(f"{f}. {o}")

    image = Image.open(tests[idx]["image_fp"])  # type: ignore

    user_answer = st.session_state.user_pic_answer.get(idx, options[0])
    user_answer_idx = options.index(user_answer)

    cols = container.columns(3)
    container.divider()
    container.markdown(question)
    container.image(image, caption=tests[idx]["iamge_label"], width=400)  # type: ignore

    container.radio(
        "选项",
        options,
        # horizontal=True,
        index=user_answer_idx,
        label_visibility="collapsed",
        # key=f"test_options_{idx}",
        on_change=on_pic_radio_change,
        args=(idx,),
        key="pic_options",
    )
    # 保存用户答案
    st.session_state.user_pic_answer[idx] = st.session_state["pic_options"]
    # container.write(f"显示 idx: {idx} 用户答案：<{st.session_state.user_answer}>")
    # my_bar.progress((idx + 1) / n, text=progress_text)
    container.divider()


def check_pic_answer(container):
    if len(st.session_state.user_pic_answer) == 0:
        st.warning("您尚未答题。")
        st.stop()

    score = 0
    tests = st.session_state.pic_tests
    n = len(tests)
    for idx in range(n):
        question = tests[idx]["question"]
        o_options = tests[idx]["options"]
        options = []
        for f, o in zip("ABC", o_options):
            options.append(f"{f}. {o}")
        answer = tests[idx]["answer"]
        image = Image.open(tests[idx]["image_fp"])  # type: ignore

        user_answer = st.session_state.user_pic_answer.get(idx, options[0])
        user_answer_idx = options.index(user_answer)
        container.divider()
        container.markdown(question)
        container.image(image, caption=tests[idx]["iamge_label"], width=400)  # type: ignore
        container.radio(
            "选项",
            options,
            # horizontal=True,
            index=user_answer_idx,
            disabled=True,
            label_visibility="collapsed",
            key=f"pic_options_{idx}",
        )
        msg = ""
        # container.write(f"显示 idx: {idx} 用户答案：{user_answer.split('.')[1]} 正确答案：{answer}")
        if user_answer.split(".")[1].strip() == answer.strip():
            score += 1
            msg = f"正确答案：{answer} :white_check_mark:"
        else:
            msg = f"正确答案：{answer} :x:"
        container.markdown(msg)
    percentage = score / n * 100
    if percentage >= 75:
        st.balloons()
    container.divider()
    container.markdown(f":red[得分：{percentage:.0f}%]")
    container.divider()


# endregion

# region 图片测词

with tabs[tab_items.index(":frame_with_picture: 图片测词")]:
    st.session_state["current_tab"] = "图片测词"
    progress_text = "图片测词进度"
    st.markdown(
        ":frame_with_picture: 图片测词是一种记忆单词的游戏，其玩法是给出一个图片，玩家需要根据图片内容来猜测图片所代表的单词。这种游戏可以帮助玩家记忆单词的含义。数据来源：[Cambridge Dictionary](https://dictionary.cambridge.org/)"
    )
    pic_cols = st.columns(4)
    category = pic_cols[0].selectbox("请选择图片类别", pic_categories)
    pic_num = pic_cols[1].number_input("请选择图片测词考题数量", 1, 20, value=10, step=1)

    st.progress(
        (st.session_state.pic_idx + 1) / pic_num,
        text=progress_text,
    )
    pic_test_cols = st.columns(6)

    # 创建按钮
    pic_test_cols[1].button(
        ":leftwards_arrow_with_hook:",
        help="点击按钮，切换到上一题。",
        on_click=on_prev_pic_btn_click,
        disabled=st.session_state.pic_idx <= 0,
    )

    pic_test_cols[2].button(
        ":arrow_right_hook:",
        help="点击按钮，切换到下一题。",
        on_click=on_next_pic_btn_click,
        disabled=st.session_state.pic_idx == pic_num - 1,
    )
    # 答题即可提交检查
    sumbit_pic_btn = pic_test_cols[3].button(
        ":mag:",
        key="submit-pic",
        disabled=len(st.session_state.pic_tests) == 0
        or len(st.session_state.user_pic_answer) == 0,
        help="至少完成一道测试题后，才可点击按钮，显示测验得分。",
    )

    if pic_test_cols[4].button(
        ":arrows_counterclockwise:", key="refresh-pic", help="点击按钮，重新生成图片测试题。"
    ):
        gen_pic_tests(category, pic_num)
        st.session_state.user_pic_answer = {}
        st.session_state.pic_idx = -1
        st.rerun()

    if len(st.session_state.pic_tests) == 0:
        gen_pic_tests(category, pic_num)

    pic_test_container = st.container()

    if sumbit_pic_btn:
        if len(st.session_state.user_pic_answer) != len(st.session_state.pic_tests):
            st.toast("您尚未完成测试。")
        check_pic_answer(pic_test_container)
    else:
        if st.session_state.current_tab == "图片测词":
            view_pic_question(pic_test_container)


# endregion

# region 个人词库辅助

add_my_word_lib_column_config = {
    "添加": st.column_config.CheckboxColumn(
        "添加",
        help="点击复选框，选中单词添加到个人词库",
        width="small",
        required=True,
    )
}

del_my_word_lib_column_config = {
    "删除": st.column_config.CheckboxColumn(
        "删除",
        help="点击复选框，从个人词库中删除该单词",
        width="small",
        required=True,
    )
}


def gen_word_lib():
    words = st.session_state.word_dict[st.session_state["selected_list"]]
    for word in words:
        if word not in st.session_state.flashcard_word_info:
            st.session_state.flashcard_word_info[word] = get_word_info(word)
    data = []
    for w in words:
        info = st.session_state.flashcard_word_info[w]
        data.append(
            {
                "单词": w,
                "CEFR最低分级": info.get("level", "") if info else "",
                "翻译": info["zh-CN"].get("translation", "") if info else "",
                "添加": False,
            }
        )
    return pd.DataFrame.from_records(data)


def gen_my_word_lib():
    my_words = st.session_state.dbi.find_personal_dictionary(
        st.session_state["user_info"]
    )
    # st.write("个人词库：", my_words)
    for word in my_words:
        if word not in st.session_state.flashcard_word_info:
            st.session_state.flashcard_word_info[word] = get_word_info(word)
    data = []
    for w in my_words:
        data.append(
            {
                "单词": w,
                "CEFR最低分级": st.session_state.flashcard_word_info[w].get("level", ""),
                "翻译": st.session_state.flashcard_word_info[w]["zh-CN"].get(
                    "translation", ""
                ),
                "删除": False,
            }
        )
    return pd.DataFrame.from_records(data)


EDITABLE_COLS: list[str] = [
    "删除",
    "添加",
]

# endregion

# region 个人词库

with tabs[tab_items.index(":books: 个人词库")]:
    lib_cols = st.columns(2)
    view_selected_list = ""
    if st.session_state["selected_list"] is not None:
        view_selected_list = st.session_state["selected_list"].split("-", maxsplit=1)[1]
    lib_cols[0].markdown(f"#### 基础词库({view_selected_list})")
    placeholder = lib_cols[0].empty()
    lib_cols[1].markdown("#### 个人词库")
    mywords_placeholder = lib_cols[1].empty()
    add_lib_btn = lib_cols[0].button(
        ":heavy_plus_sign:", key="add-lib-btn", help="点击按钮，将'基础词库'中已选单词添加到个人词库。"
    )
    del_lib_btn = lib_cols[1].button(
        ":heavy_minus_sign:", key="del-lib-btn", help="点击按钮，将已选单词从'个人词库'中删除。"
    )
    df = gen_word_lib()
    edited_df = placeholder.data_editor(
        df,
        key="word_lib",
        hide_index=True,
        column_config=add_my_word_lib_column_config,
        height=500,
        disabled=[col for col in df.columns if col not in EDITABLE_COLS],
    )
    if add_lib_btn and st.session_state.get("word_lib", None):
        word_lib = st.session_state["word_lib"]
        edited_rows = word_lib["edited_rows"]
        # st.write("编辑的行：", edited_rows)
        for idx, d in edited_rows.items():
            word = df.iloc[idx]["单词"]  # type: ignore
            if d["添加"]:
                st.session_state.dbi.add_word_to_personal_dictionary(
                    st.session_state["user_info"], word
                )
                st.toast(f"已添加到个人词库中：{word}。")

        word_lib["edited_rows"] = {}

    my_word_df = gen_my_word_lib()
    mywords_placeholder.data_editor(
        my_word_df,
        key="my_word_lib",
        hide_index=True,
        column_config=del_my_word_lib_column_config,
        height=500,
        disabled=[col for col in df.columns if col not in EDITABLE_COLS],
    )

    if del_lib_btn and st.session_state.get("my_word_lib", None):
        my_word_lib = st.session_state["my_word_lib"]
        my_word_edited_rows = my_word_lib["edited_rows"]
        # st.write("编辑的行：", edited_rows)
        for idx, d in my_word_edited_rows.items():
            word = my_word_df.iloc[idx]["单词"]  # type: ignore
            if d["删除"]:
                st.session_state.dbi.remove_word_from_personal_dictionary(
                    st.session_state["user_info"], word
                )
                st.toast(f"已从个人词库中删除：{word}。")
        st.rerun()

# endregion

# region 单词测验辅助

if "test_idx" not in st.session_state:
    st.session_state["test_idx"] = -1


if "tests" not in st.session_state:
    st.session_state["tests"] = []

if "user_answer" not in st.session_state:
    st.session_state["user_answer"] = {}


def on_prev_test_btn_click():
    st.session_state["test_idx"] -= 1


def on_next_test_btn_click():
    st.session_state["test_idx"] += 1


@st.spinner("AI🤖正在生成单词理解测试题，请稍候...")
def gen_test(level, test_num):
    words = random.sample(st.session_state.flashcard_words, test_num)
    for word in words:
        st.session_state.tests.append(generate_word_test(word, level))


def check_answer(test_container):
    if len(st.session_state.user_answer) == 0:
        st.warning("您尚未答题。")
        st.stop()

    score = 0
    n = len(st.session_state.tests)
    for idx in range(n):
        question = st.session_state.tests[idx]["question"]
        options = st.session_state.tests[idx]["options"]
        answer = st.session_state.tests[idx]["answer"]
        explanation = st.session_state.tests[idx]["explanation"]

        user_answer = st.session_state.user_answer.get(idx, options[0])
        user_answer_idx = options.index(user_answer)
        test_container.divider()
        test_container.markdown(question)
        test_container.radio(
            "选项",
            options,
            # horizontal=True,
            index=user_answer_idx,
            disabled=True,
            label_visibility="collapsed",
            key=f"test_options_{idx}",
        )
        msg = ""
        # 用户答案是选项，而提供的标准答案是A、B、C、D
        if user_answer.split(".")[0] == answer:
            score += 1
            msg = f"正确答案：{answer} :white_check_mark:"
        else:
            msg = f"正确答案：{answer} :x:"
        test_container.markdown(msg)
        test_container.markdown(f"解释：{explanation}")
    percentage = score / n * 100
    if percentage >= 75:
        st.balloons()
    test_container.divider()
    test_container.markdown(f":red[得分：{percentage:.0f}%]")
    test_container.divider()


def on_radio_change(idx):
    # 保存用户答案
    st.session_state.user_answer[idx] = st.session_state["test_options"]


def view_question(test_container):
    if len(st.session_state.tests) == 0:
        return

    progress_text = "答题进度"
    n = len(st.session_state.tests)
    idx = st.session_state.test_idx
    question = st.session_state.tests[idx]["question"]
    options = st.session_state.tests[idx]["options"]
    user_answer = st.session_state.user_answer.get(idx, options[0])
    user_answer_idx = options.index(user_answer)

    cols = test_container.columns(3)
    my_bar = cols[0].progress(0, text=progress_text)
    test_container.divider()
    test_container.markdown(question)
    test_container.radio(
        "选项",
        options,
        # horizontal=True,
        index=user_answer_idx,
        label_visibility="collapsed",
        # key=f"test_options_{idx}",
        on_change=on_radio_change,
        args=(
            test_container,
            idx,
        ),
        key="test_options",
    )
    # 保存用户答案
    st.session_state.user_answer[idx] = st.session_state["test_options"]
    # test_container.write(f"显示 idx: {idx} 用户答案：<{st.session_state.user_answer}>")
    my_bar.progress((idx + 1) / n, text=progress_text)
    test_container.divider()


# endregion

# region 单词测验

with tabs[tab_items.index(":memo: 单词测验")]:
    st.info("试题词汇来源于【记忆闪卡】生成的单词列表。")
    cols = st.columns(4)
    level = cols[0].selectbox("单词级别", ("A1", "A2", "B1", "B2", "C1", "C2"))

    test_num = cols[1].number_input("试题数量", 1, 20, value=10, step=1)

    test_container = st.container()

    test_btns = st.columns(6)
    gen_test_btn = test_btns[1].button(
        ":arrows_counterclockwise:", key="gen-test", help="点击按钮，生成单词理解测试题。"
    )
    prev_test_btn = test_btns[2].button(
        ":leftwards_arrow_with_hook:",
        key="prev-test",
        help="点击按钮，切换到上一题。",
        on_click=on_prev_test_btn_click,
        args=(test_container,),
        disabled=st.session_state.test_idx <= 0,
    )
    next_test_btn = test_btns[3].button(
        ":arrow_right_hook:",
        key="next-test",
        help="点击按钮，切换到下一题。",
        on_click=on_next_test_btn_click,
        args=(test_container,),
        disabled=st.session_state.test_idx == test_num - 1,
    )
    # 答题即可提交检查
    sumbit_test_btn = test_btns[4].button(
        ":mag:",
        key="submit-test",
        disabled=len(st.session_state.tests) == 0
        or len(st.session_state.user_answer) == 0,
        help="至少完成一道测试题后，才可点击按钮，显示测验得分。",
    )

    if gen_test_btn:
        # 重置考题
        st.session_state.test_idx = 0
        st.session_state.user_answer = {}
        st.session_state.tests = []
        test_container.empty()
        gen_test(level, test_num)

    if sumbit_test_btn:
        if len(st.session_state.user_answer) != len(st.session_state.tests):
            st.toast("您尚未完成测试。")
        check_answer(test_container)
    else:
        view_question(test_container)


# endregion
