import json
import logging
import os
import random
import re
from pathlib import Path

import google.generativeai as palm
import streamlit as st
import streamlit.components.v1 as components

from mypylib.authenticate import DbInterface
from mypylib.azure_speech import synthesize_speech_to_file
from mypylib.google_api import (
    generate_word_memory_tip,
    get_translation_client,
    google_translate,
    init_vertex,
)

# 使用 vertex ai
from mypylib.google_palm import (
    gen_vocabulary_comprehension_test,
    get_irregular_forms_of_a_word,
    lemmatize,
    lookup,
)
from mypylib.word_utils import hash_word, mp3_autoplay_elem

# 创建或获取logger对象
logger = logging.getLogger("streamlit")

# 设置日志级别
logger.setLevel(logging.DEBUG)

# region 常量
# streamlit中各页都是相对当前根目录
# palm.configure(api_key=st.secrets["Google"]["PALM_API_KEY"])
current_cwd: Path = Path(__file__).parent.parent
DICT_DIR = current_cwd / "resource/dictionary"

# endregion

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

# endregion

# region 会话状态

st.set_page_config(
    page_title="记忆单词",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="auto",
)

if "words_to_memorize" not in st.session_state:
    st.session_state["words_to_memorize"] = []

if "words" not in st.session_state:
    st.session_state["words"] = {}

if "display_state" not in st.session_state:
    st.session_state["display_state"] = "全部"

# 初始化单词的索引
if "word_idx" not in st.session_state:
    st.session_state["word_idx"] = -1


# endregion

# region 事件及函数


def on_prev_btn_click():
    st.session_state["word_idx"] -= 1


def on_next_btn_click():
    st.session_state["word_idx"] += 1


def gen_words_to_memorize():
    # 获取选中的单词列表
    words = word_lists[selected_list]
    num_words = st.session_state["num_words_key"]
    # 随机选择单词
    st.session_state.words_to_memorize = random.sample(words, num_words)
    # st.write("单词:", st.session_state.words_to_memorize)
    # 恢复初始显示状态
    st.session_state.display_state = "全部"
    st.session_state["word_idx"] = -1
    # st.write("临时测试：单词数量", len(st.session_state.words_to_memorize))


def gen_audio_fp(word: str, style: str):
    # 生成单词的哈希值
    hash_value = hash_word(word)

    # 生成单词的语音文件名
    audio_dir = os.path.join(current_cwd, f"resource/word_voices/{style}")
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
            st.secrets["Microsoft"]["SPEECH_SERVICE_REGION"],
            style,  # type: ignore
        )
    return audio_fp


@st.cache_data
def get_word_info(word):
    return st.session_state.dbi.find_word(word)


# endregion

# region 侧边栏

# 加载单词列表
with open(DICT_DIR / "word_lists_by_edition_grade.json", "r", encoding="utf-8") as f:
    word_lists = json.load(f)

with open(current_cwd / "resource/voices.json", "r", encoding="utf-8") as f:
    voice_style_options = json.load(f)


# 让用户选择语音风格
pronunciation = st.sidebar.radio("请选择发音标准", ("美式", "英式"))
style = "en-US" if pronunciation == "美式" else "en-GB"

# voice_style = st.sidebar.selectbox(
#     "请选择发音风格", voice_style_options[style], format_func=lambda x: f"{x[0]}({x[1]})"
# )

# 固定语音风格
voice_style = voice_style_options[style][0]
st.sidebar.info(f"语音风格是：{voice_style[0]}({voice_style[1]})")

# 在侧边栏添加一个选项卡让用户选择一个单词列表
selected_list = st.sidebar.selectbox(
    "请选择一个单词列表", sorted(list(word_lists.keys())), on_change=gen_words_to_memorize
)

# 在侧边栏添加一个滑块让用户选择记忆的单词数量
st.sidebar.slider(
    "请选择计划记忆的单词数量", 10, 50, step=5, key="num_words_key", on_change=gen_words_to_memorize
)

# endregion

# region 页面
items = ["📖 闪卡记忆", "🧩 单词拼图", "图片测词", "单词测验", "统计"]
tabs = st.tabs(items)
# endregion

# region 记忆闪卡

if len(st.session_state.words_to_memorize) == 0:
    gen_words_to_memorize()

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
        container.markdown(f"definition：**{d1}**")
        container.markdown(f"定义：**{d2}**")
        # container.markdown("-" * num)

        content = ""
        for e, t in zip(e1, e2):
            content += f"- {_rainbow_word(e, word)}\n"
            content += f"- {t}\n"
        container.markdown(content)
    elif st.session_state.display_state == "英文":
        container.markdown(f"definition：**{d1}**")
        # container.markdown("-" * num)

        content = ""
        for e in e1:
            content += f"- {_rainbow_word(e, word)}\n"
        container.markdown(content)
    else:
        # 只显示译文
        container.markdown(f"定义：**{d2}**")
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


def view_word(container, tip_placeholder, word):
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


with tabs[items.index("📖 闪卡记忆")]:
    btn_cols = st.columns(12)
    word = st.session_state.words_to_memorize[st.session_state.word_idx]
    tip_placeholder = st.empty()
    container = st.container()

    # placeholder = st.container()
    # 创建前后选择的按钮
    mask_btn = btn_cols[0].button(
        "♻️", key="mask", help="点击按钮，可切换显示状态。初始状态显示中英对照。点击按钮，切换为只显示英文。再次点击按钮，切换为只显示中文。"
    )
    prev_btn = btn_cols[1].button(
        "↩️",
        key="prev",
        help="点击按钮，切换到上一个单词。",
        on_click=on_prev_btn_click,
        disabled=st.session_state.word_idx <= 0,
    )
    next_btn = btn_cols[2].button(
        "↪️",
        key="next",
        help="点击按钮，切换到下一个单词。",
        on_click=on_next_btn_click,
        disabled=st.session_state.word_idx
        == len(st.session_state.words_to_memorize) - 1,
    )
    play_btn = btn_cols[3].button("🔊", key="play", help="聆听单词发音")
    add_btn = btn_cols[4].button("➕", key="add", help="添加到个人词库")
    del_btn = btn_cols[5].button("➖", key="del", help="从个人词库中删除")
    refresh_btn = btn_cols[6].button("🔄", key="refresh", help="重新生成单词列表")

    placeholder = st.empty()

    # 创建按钮
    if mask_btn:
        if st.session_state.display_state == "全部":
            st.session_state.display_state = "英文"
        elif st.session_state.display_state == "英文":
            st.session_state.display_state = "中文"
        else:
            st.session_state.display_state = "全部"
        view_word(container, tip_placeholder, word)

    if prev_btn:
        # 点击后会重新随机选择，需要使用会话状态管理
        view_word(container, tip_placeholder, word)

    if next_btn:
        # 点击后会重新随机选择，需要使用会话状态管理
        view_word(container, tip_placeholder, word)

    if play_btn:
        word = st.session_state.words_to_memorize[st.session_state.word_idx]
        fp = gen_audio_fp(st.session_state.words_to_memorize[st.session_state.word_idx], voice_style[0])  # type: ignore
        # placeholder.text(fp)
        components.html(mp3_autoplay_elem(fp))
        view_word(container, tip_placeholder, word)

    if refresh_btn:
        gen_words_to_memorize()

    if add_btn:
        word = st.session_state.words_to_memorize[st.session_state.word_idx]
        st.session_state.dbi.add_to_personal_dictionary(
            st.session_state["user_id"], word
        )
        st.toast(f"已添加单词：{word}到个人词库。")

    if del_btn:
        word = st.session_state.words_to_memorize[st.session_state.word_idx]
        st.session_state.dbi.remove_from_personal_dictionary(
            st.session_state["user_id"], word
        )
        st.toast(f"已从个人词库中删除单词：{word}。")

# endregion


# region 单词拼图

if "puzzle_idx" not in st.session_state:
    st.session_state["puzzle_idx"] = -1

if "words_to_puzzle" not in st.session_state:
    st.session_state["words_to_puzzle"] = []

if "puzzle_view_word" not in st.session_state:
    st.session_state["puzzle_view_word"] = []

if "clicked_character" not in st.session_state:
    st.session_state["clicked_character"] = []


def gen_words_to_puzzle():
    # 获取选中的单词列表
    words = word_lists[selected_list]
    num_words = st.session_state["num_words_key"]
    # 随机选择单词
    st.session_state.words_to_puzzle = random.sample(words, num_words)
    # 恢复初始显示状态
    st.session_state.puzzle_idx = -1
    st.session_state["puzzle_view_word"] = []


def get_word_definition(word):
    word_info = get_word_info(word)
    definition = ""
    en = word_info["en-US"]
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
    st.session_state.puzzle_answer = ""


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
            st.session_state.puzzle_answer += ws[i]
            st.session_state.clicked_character[i] = True


def view_definition(progress_placeholder):
    if len(st.session_state.puzzle_view_word) == 0:
        gen_words_to_puzzle()
    n = len(st.session_state.words_to_puzzle)
    progress_placeholder.progress(
        (st.session_state.puzzle_idx + 1) / n, text="🧩 单词拼图进度"
    )
    word = st.session_state.words_to_puzzle[st.session_state.puzzle_idx]
    definition = get_word_definition(word)
    st.write("单词释义：")
    st.markdown(definition)


def on_prev_puzzle_btn_click():
    st.session_state["puzzle_idx"] -= 1


def on_next_puzzle_btn_click():
    st.session_state["puzzle_idx"] += 1


with tabs[items.index("🧩 单词拼图")]:
    p_progress_text = "进度"
    n = st.session_state["num_words_key"]
    progress_placeholder = st.empty()
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

    view_definition(progress_placeholder)
    view_puzzle_word()
    user_input = st.text_input("点击字符按钮或输入您的答案", key="puzzle_answer")

    if st.button("检查", help="点击按钮，检查您的答案。"):
        word = st.session_state.words_to_puzzle[st.session_state.puzzle_idx]
        if word not in st.session_state.words:
            st.session_state.words[word] = get_word_info(word)

        if user_input == word:
            st.balloons()
        else:
            st.write(
                f'对不起，您回答错误。正确的单词应该为：{word}，翻译：{st.session_state.words[word]["zh-CN"]["translation"]}'
            )

# endregion

# region 图片测词
# endregion

# region 单词测验


if "test_idx" not in st.session_state:
    st.session_state["test_idx"] = -1


if "tests" not in st.session_state:
    st.session_state["tests"] = []

if "user_answer" not in st.session_state:
    st.session_state["user_answer"] = {}


def on_prev_test_btn_click(test_container):
    st.session_state["test_idx"] -= 1


def on_next_test_btn_click(test_container):
    st.session_state["test_idx"] += 1


@st.spinner("AI🤖正在生成单词理解测试题，请稍候...")
def gen_test(level, test_num):
    words = random.sample(st.session_state.words_to_memorize, test_num)
    for word in words:
        st.session_state.tests.append(gen_vocabulary_comprehension_test(word, level))


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
            msg = f"正确答案：{answer} ➕"
        else:
            msg = f"正确答案：{answer} ❌"
        test_container.markdown(msg)
        test_container.markdown(f"解释：{explanation}")
    percentage = score / n * 100
    if percentage >= 75:
        st.balloons()
    test_container.divider()
    test_container.text(f"得分：{percentage:.0f}%")
    test_container.divider()


def on_radio_change(test_container, idx):
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


with tabs[items.index("单词测验")]:
    st.info("试题词汇来源于【记忆闪卡】生成的单词列表。")
    cols = st.columns(6)
    level = cols[0].selectbox("单词级别", ("A1", "A2", "B1", "B2", "C1", "C2"))

    test_num = cols[1].number_input("试题数量", 1, 20, value=10, step=1)

    test_container = st.container()

    test_btns = st.columns(8)
    gen_test_btn = test_btns[0].button("🔄", key="gen-test", help="点击按钮，生成单词理解测试题。")
    prev_test_btn = test_btns[1].button(
        "↩️",
        key="prev-test",
        help="点击按钮，切换到上一题。",
        on_click=on_prev_test_btn_click,
        args=(test_container,),
        disabled=st.session_state.test_idx <= 0,
    )
    next_test_btn = test_btns[2].button(
        "↪️",
        key="next-test",
        help="点击按钮，切换到下一题。",
        on_click=on_next_test_btn_click,
        args=(test_container,),
        disabled=st.session_state.test_idx == test_num - 1,
    )
    # 答题即可提交检查
    sumbit_test_btn = test_btns[3].button(
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
