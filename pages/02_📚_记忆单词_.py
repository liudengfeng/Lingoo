import json
import logging
import os
import random
import re
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from mypylib.azure_speech import synthesize_speech_to_file
from mypylib.db_interface import DbInterface
from mypylib.google_api import (
    generate_word_memory_tip,
    generate_word_test,
    get_translation_client,
    google_translate,
)
from mypylib.streamlit_helper import authenticate, check_and_force_logout
from mypylib.word_utils import audio_autoplay_elem, hash_word

# 创建或获取logger对象
logger = logging.getLogger("streamlit")

# region 常量
# streamlit中各页都是相对当前根目录

CURRENT_CWD: Path = Path(__file__).parent.parent
DICT_DIR = CURRENT_CWD / "resource/dictionary"

# endregion

# region 认证及初始化

authenticate(st)


if len(st.session_state.get("word_lists", {})) == 0:
    with open(
        DICT_DIR / "word_lists_by_edition_grade.json", "r", encoding="utf-8"
    ) as f:
        st.session_state["word_lists"] = json.load(f)

if "current_word_lib" not in st.session_state:
    st.session_state["current_word_lib"] = []

if "flashcard_words" not in st.session_state:
    st.session_state["flashcard_words"] = []

if "words" not in st.session_state:
    st.session_state["words"] = {}

if "display_state" not in st.session_state:
    st.session_state["display_state"] = "全部"

# 初始化单词的索引
if "current_flashcard_word_index" not in st.session_state:
    st.session_state["current_flashcard_word_index"] = -1
# endregion

# region 页设置

st.set_page_config(
    page_title="记忆单词",
    page_icon="📚",
    layout="wide",
)

# endregion

# region 事件及函数


def on_word_lib_changed():
    word_lib_name = st.session_state["selected_list"]
    st.session_state.current_word_lib = st.session_state.word_lists[word_lib_name]


def generate_flashcard_words():
    # 获取选中的单词列表
    words = st.session_state.current_word_lib
    num_words = st.session_state["num_words_key"]
    n = min(num_words, len(words))
    # 随机选择单词
    st.session_state.flashcard_words = random.sample(words, n)
    # st.write("单词:", st.session_state.flashcard_words)
    # 恢复初始显示状态
    # st.session_state.display_state = "全部"
    # st.session_state["current_flashcard_word_index"] = -1


def gen_audio_fp(word: str, style: str):
    # 生成单词的哈希值
    hash_value = hash_word(word)

    # 生成单词的语音文件名
    audio_dir = os.path.join(CURRENT_CWD, f"resource/word_voices/{style}")
    if not os.path.exists(audio_dir):
        os.makedirs(audio_dir)

    filename = f"e{hash_value}.mp3"
    audio_fp = os.path.join(audio_dir, filename)

    # 如果语音文件不存在，则调用Azure的语音合成服务生成语音文件
    if not os.path.exists(audio_fp):
        synthesize_speech_to_file(
            word,
            audio_fp,
            st.secrets["Microsoft"]["SPEECH_KEY"],
            st.secrets["Microsoft"]["SPEECH_REGION"],
            style,  # type: ignore
        )
    return audio_fp


@st.cache_data
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
        st.session_state.word_lists["0-个人词库"] = personal_word_list

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
    sorted(list(st.session_state.word_lists.keys())),
    key="selected_list",
    on_change=on_word_lib_changed,
    format_func=lambda x: x.split("-", maxsplit=1)[1],
)


# 在侧边栏添加一个滑块让用户选择记忆的单词数量

st.sidebar.slider(
    "请选择计划记忆的单词数量",
    10,
    50,
    step=5,
    key="num_words_key",
    # on_change=generate_flashcard_words
)

# endregion

# region tabs
# 将二者分离，避免格式经常被重置
tab_names = ["记忆闪卡", "单词拼图", "图片测词", "单词测验", "个人词库", "个人统计"]
tab_emoji = ["📖", "🧩", "🖼️", "📝", "📚", "📊"]
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
- CEFR：:green[{cefr}]
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
    num = 10
    d1 = detail["definition"]
    e1 = detail["examples"]
    d2 = t_detail["definition"]
    e2 = t_detail["examples"]
    if st.session_state.display_state == "全部":
        container.markdown(f"definition：**{d1[:-1]}**")
        container.markdown(f"定义：**{d2[:-1]}**")
        # container.markdown("-" * num)

        content = ""
        for e, t in zip(e1, e2):
            content += f"- {_rainbow_word(e, word)}\n"
            content += f"- {t}\n"
        container.markdown(content)
    elif st.session_state.display_state == "英文":
        container.markdown(f"definition：**{d1[:-1]}**")
        # container.markdown("-" * num)

        content = ""
        for e in e1:
            content += f"- {_rainbow_word(e, word)}\n"
        container.markdown(content)
    else:
        # 只显示译文
        container.markdown(f"定义：**{d2[:-1]}**")
        # container.markdown("-" * num)
        content = ""
        for e in e2:
            content += f"- {e}\n"
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


@st.cache_data(ttl=60 * 60 * 2, show_spinner="获取 Ai 提示...")
def _memory_tip(word):
    return generate_word_memory_tip(word)


def view_flash_word(container, tip_placeholder):
    if st.session_state.current_flashcard_word_index == -1:
        return

    if len(st.session_state.flashcard_words) == 0:
        generate_flashcard_words()

    word = st.session_state.flashcard_words[
        st.session_state.current_flashcard_word_index
    ]
    if word not in st.session_state.words:
        st.session_state.words[word] = get_word_info(word)

    word_info = st.session_state.words.get(word, {})
    if word_info is None:
        st.error(f"没有该单词：“{word}”的信息。TODO：添加到单词库。")
        st.stop()

    if st.secrets.get("dev", "") in ["streamlit", "azure"]:
        with tip_placeholder.expander("记忆提示"):
            # 生成记忆提示
            memory_tip = _memory_tip(word)
            st.markdown(memory_tip)

    v_word = word
    t_word = ""
    if st.session_state.display_state == "中文":
        v_word = ""

    if st.session_state.display_state != "英文":
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

with tabs[tab_items.index("📖 记忆闪卡")]:
    btn_cols = st.columns(9)
    tip_placeholder = st.empty()
    container = st.container()

    # placeholder = st.container()
    # 创建前后选择的按钮
    display_status_button = btn_cols[1].button(
        "♻️", key="mask", help="点击按钮，可切换显示状态。初始状态显示中英对照。点击按钮，切换为只显示英文。再次点击按钮，切换为只显示中文。"
    )
    prev_btn = btn_cols[2].button(
        "↩️",
        key="prev",
        help="点击按钮，切换到上一个单词。",
        on_click=on_prev_btn_click,
        disabled=st.session_state.current_flashcard_word_index <= 0,
    )
    next_btn = btn_cols[3].button(
        "↪️",
        key="next",
        help="点击按钮，切换到下一个单词。",
        on_click=on_next_btn_click,
        disabled=len(st.session_state.flashcard_words)
        and st.session_state.current_flashcard_word_index
        == len(st.session_state.flashcard_words) - 1,
    )

    play_btn = btn_cols[4].button("🔊", key="play", help="聆听单词发音")
    add_btn = btn_cols[5].button("➕", key="add", help="添加到个人词库")
    del_btn = btn_cols[6].button("➖", key="del", help="从个人词库中删除")
    refresh_btn = btn_cols[7].button("🔄", key="refresh", help="重新生成单词列表")

    placeholder = st.empty()

    # 创建按钮
    if display_status_button:
        if st.session_state.display_state == "全部":
            st.session_state.display_state = "英文"
        elif st.session_state.display_state == "英文":
            st.session_state.display_state = "中文"
        else:
            st.session_state.display_state = "全部"

    if play_btn:
        word = st.session_state.flashcard_words[
            st.session_state.current_flashcard_word_index
        ]
        fp = gen_audio_fp(st.session_state.flashcard_words[st.session_state.current_flashcard_word_index], voice_style[0])  # type: ignore
        # placeholder.text(fp)
        components.html(audio_autoplay_elem(fp))
        # view_flash_word(container, tip_placeholder)

    if refresh_btn:
        generate_flashcard_words()

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

    view_flash_word(container, tip_placeholder)

# endregion

# region 单词拼图辅助

if "puzzle_idx" not in st.session_state:
    st.session_state["puzzle_idx"] = -1

if "words_to_puzzle" not in st.session_state:
    st.session_state["words_to_puzzle"] = []

if "puzzle_answer_value" not in st.session_state:
    st.session_state["puzzle_answer_value"] = ""

if "puzzle_view_word" not in st.session_state:
    st.session_state["puzzle_view_word"] = []

if "clicked_character" not in st.session_state:
    st.session_state["clicked_character"] = []

if "puzzle_test_score" not in st.session_state:
    st.session_state["puzzle_test_score"] = {}


def gen_words_to_puzzle():
    # 获取选中的单词列表
    words = st.session_state.word_lists[st.session_state["selected_list"]]
    num_words = st.session_state["num_words_key"]
    n = min(num_words, len(words))
    # 随机选择单词
    st.session_state.words_to_puzzle = random.sample(words, n)
    # 恢复初始显示状态
    st.session_state.puzzle_idx = 0
    st.session_state["puzzle_view_word"] = []


def get_word_definition(word):
    word_info = get_word_info(word)
    definition = ""
    en = word_info.get("en-US", {})
    for k, v in en.items():
        definition += f"\n{k}\n"
        for d in v:
            definition += f'- {d["definition"]}\n'
    return definition


def init_puzzle():
    word = st.session_state.words_to_puzzle[st.session_state.puzzle_idx]
    ws = [w for w in word]
    random.shuffle(ws)
    st.session_state.puzzle_view_word = ws
    st.session_state.clicked_character = [False] * len(ws)
    st.session_state.puzzle_answer_value = ""


def view_puzzle_word():
    if len(st.session_state.puzzle_view_word) == 0:
        init_puzzle()

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


def view_definition(progress_word):
    if len(st.session_state.puzzle_view_word) == 0:
        gen_words_to_puzzle()
    n = len(st.session_state.words_to_puzzle)
    progress = 1.0 * (st.session_state.puzzle_idx + 1) / n
    # st.write("进度：", progress, "idx", st.session_state.puzzle_idx)
    progress_word.progress(progress, text="🧩 单词拼图进度")
    word = st.session_state.words_to_puzzle[st.session_state.puzzle_idx]
    definition = get_word_definition(word)
    st.write("参考信息：")
    st.markdown(definition)


def on_prev_puzzle_btn_click():
    st.session_state["puzzle_idx"] -= 1


def on_next_puzzle_btn_click():
    st.session_state["puzzle_idx"] += 1


# endregion

# region 单词拼图

with tabs[tab_items.index("🧩 单词拼图")]:
    st.markdown(
        "单词拼图是一种记忆单词的游戏。数据来源：[Cambridge Dictionary](https://dictionary.cambridge.org/)"
    )
    p_progress_text = "进度"
    n = st.session_state["num_words_key"]
    progress_word = st.empty()
    p_btns = st.columns(4)
    prev_p_btn = p_btns[1].button(
        "↩️",
        key="prev-puzzle",
        help="点击按钮，切换到上一单词拼图。",
        on_click=on_prev_puzzle_btn_click,
        disabled=st.session_state.puzzle_idx <= 0,
    )
    next_test_btn = p_btns[2].button(
        "↪️",
        key="next-puzzle",
        help="点击按钮，切换到下一单词拼图。",
        on_click=on_next_puzzle_btn_click,
        disabled=st.session_state.puzzle_idx == n - 1,
    )

    refresh_btn = p_btns[3].button("🔄", key="refresh-puzzle", help="重新生成单词列表")

    if prev_p_btn:
        init_puzzle()

    if next_test_btn:
        init_puzzle()

    if refresh_btn:
        gen_words_to_puzzle()

    view_definition(progress_word)
    view_puzzle_word()

    user_input = st.text_input(
        "点击字符按钮或输入您的答案",
        placeholder="点击字符按钮或输入您的答案",
        value=st.session_state.puzzle_answer_value,
        key="puzzle_answer",
        label_visibility="collapsed",
    )
    puzzle_score = st.empty()
    sumbit_cols = st.columns(6)
    if sumbit_cols[0].button("重试", help="恢复初始状态，重新开始。"):
        init_puzzle()
        st.rerun()

    if sumbit_cols[1].button("检查", help="点击按钮，检查您的答案是否正确。"):
        word = st.session_state.words_to_puzzle[st.session_state.puzzle_idx]
        if word not in st.session_state.words:
            st.session_state.words[word] = get_word_info(word)

        if user_input == word:
            st.balloons()
            st.session_state.puzzle_test_score[word] = True
        else:
            st.write(
                f'对不起，您回答错误。正确的单词应该为：{word}，翻译：{st.session_state.words[word]["zh-CN"]["translation"]}'
            )
            st.session_state.puzzle_test_score[word] = False

        if st.session_state.puzzle_idx == n - 1:
            score = sum(st.session_state.puzzle_test_score.values()) / n * 100
            msg = f":red[您的得分：{score:.0f}%]"
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


def gen_pic_qa(category, num):
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
    st.session_state.user_pic_answer = {}
    st.session_state["pic_idx"] = -1


def on_pic_radio_change(idx):
    # 保存用户答案
    st.session_state.user_pic_answer[idx] = st.session_state["pic_options"]


def view_pic_question(container):
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
    # my_bar = cols[0].progress(0, text=progress_text)
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
            msg = f"正确答案：{answer} ✅"
        else:
            msg = f"正确答案：{answer} ❌"
        container.markdown(msg)
    percentage = score / n * 100
    if percentage >= 75:
        st.balloons()
    container.divider()
    container.markdown(f":red[得分：{percentage:.0f}%]")
    container.divider()


# endregion

# region 图片测词

with tabs[tab_items.index("🖼️ 图片测词")]:
    progress_text = "图片测词进度"
    st.markdown(
        "🖼️ 图片测词是一种记忆单词的游戏。数据来源：[Cambridge Dictionary](https://dictionary.cambridge.org/)"
    )
    pic_cols = st.columns(4)
    category = pic_cols[0].selectbox("请选择图片类别", pic_categories)
    pic_num = pic_cols[1].number_input("请选择图片测词考题数量", 1, 20, value=10, step=1)
    my_bar = st.progress((st.session_state["pic_idx"] + 1) / n, text=progress_text)
    pic_qa_cols = st.columns(6)
    pic_idx = st.session_state.get("pic_idx", 0)  # 获取当前问题的索引

    # 创建按钮
    pic_qa_cols[1].button(
        "↩️", help="点击按钮，切换到上一题。", on_click=on_prev_pic_btn_click, disabled=pic_idx <= 0
    )

    pic_qa_cols[2].button(
        "↪️",
        help="点击按钮，切换到下一题。",
        on_click=on_next_pic_btn_click,
        disabled=pic_idx == pic_num - 1,
    )
    # 答题即可提交检查
    sumbit_pic_btn = pic_qa_cols[3].button(
        "🔍",
        key="submit-pic",
        disabled=len(st.session_state.pic_tests) == 0
        or len(st.session_state.user_pic_answer) == 0,
        help="至少完成一道测试题后，才可点击按钮，显示测验得分。",
    )

    if pic_qa_cols[4].button("🔄", key="refresh-pic", help="点击按钮，重新生成考题。"):
        gen_pic_qa(category, pic_num)

    if len(st.session_state.pic_tests) == 0:
        gen_pic_qa(category, pic_num)

    pic_qa_container = st.container()

    if sumbit_pic_btn:
        if len(st.session_state.user_pic_answer) != len(st.session_state.pic_tests):
            st.toast("您尚未完成测试。")
        check_pic_answer(pic_qa_container)
    else:
        view_pic_question(pic_qa_container)


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
    words = st.session_state.word_lists[st.session_state["selected_list"]]
    for word in words:
        if word not in st.session_state.words:
            st.session_state.words[word] = get_word_info(word)
    data = []
    for w in words:
        info = st.session_state.words[w]
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
        if word not in st.session_state.words:
            st.session_state.words[word] = get_word_info(word)
    data = []
    for w in my_words:
        data.append(
            {
                "单词": w,
                "CEFR最低分级": st.session_state.words[w].get("level", ""),
                "翻译": st.session_state.words[w]["zh-CN"].get("translation", ""),
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

with tabs[tab_items.index("📚 个人词库")]:
    lib_cols = st.columns(2)
    view_selected_list = ""
    if st.session_state["selected_list"] is not None:
        view_selected_list = st.session_state["selected_list"].split("-", maxsplit=1)[1]
    lib_cols[0].markdown(f"#### 基础词库({view_selected_list})")
    placeholder = lib_cols[0].empty()
    lib_cols[1].markdown("#### 个人词库")
    mywords_placeholder = lib_cols[1].empty()
    add_lib_btn = lib_cols[0].button(
        "➕", key="add-lib-btn", help="点击按钮，将'基础词库'中已选单词添加到个人词库。"
    )
    del_lib_btn = lib_cols[1].button(
        "➖", key="del-lib-btn", help="点击按钮，将已选单词从'个人词库'中删除。"
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
            msg = f"正确答案：{answer} ✅"
        else:
            msg = f"正确答案：{answer} ❌"
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

with tabs[tab_items.index("📝 单词测验")]:
    st.info("试题词汇来源于【记忆闪卡】生成的单词列表。")
    cols = st.columns(4)
    level = cols[0].selectbox("单词级别", ("A1", "A2", "B1", "B2", "C1", "C2"))

    test_num = cols[1].number_input("试题数量", 1, 20, value=10, step=1)

    test_container = st.container()

    test_btns = st.columns(6)
    gen_test_btn = test_btns[1].button("🔄", key="gen-test", help="点击按钮，生成单词理解测试题。")
    prev_test_btn = test_btns[2].button(
        "↩️",
        key="prev-test",
        help="点击按钮，切换到上一题。",
        on_click=on_prev_test_btn_click,
        args=(test_container,),
        disabled=st.session_state.test_idx <= 0,
    )
    next_test_btn = test_btns[3].button(
        "↪️",
        key="next-test",
        help="点击按钮，切换到下一题。",
        on_click=on_next_test_btn_click,
        args=(test_container,),
        disabled=st.session_state.test_idx == test_num - 1,
    )
    # 答题即可提交检查
    sumbit_test_btn = test_btns[4].button(
        "🔍",
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
