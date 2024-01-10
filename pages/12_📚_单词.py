import json
import logging
import os
import random
import re
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import PIL.Image
from vertexai.preview.generative_models import Image

from mypylib.constants import CEFR_LEVEL_MAPS
from mypylib.google_ai import generate_word_test, select_best_images_for_word
from mypylib.st_helper import (
    check_access,
    check_and_force_logout,
    configure_google_apis,
    load_vertex_model,
    setup_logger,
    update_and_display_progress,
)
from mypylib.word_utils import (
    audio_autoplay_elem,
    get_or_create_and_return_audio_data,
    get_word_image_urls,
    load_image_bytes_from_url,
    remove_trailing_punctuation,
)

# 创建或获取logger对象
logger = logging.getLogger("streamlit")
setup_logger(logger)

# region 页设置

st.set_page_config(
    page_title="记忆单词",
    page_icon=":books:",
    layout="wide",
)

check_access(False)
configure_google_apis()
sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(sidebar_status)

menu_names = ["闪卡记忆", "拼图游戏", "看图测词", "词义理解", "词库管理"]
menu_emoji = [
    "📚",
    "🧩",
    "🖼️",
    "📝",
    "🗂️",
]
menu_opts = [e + " " + n for e, n in zip(menu_emoji, menu_names)]
menu = st.sidebar.selectbox("菜单", menu_opts, help="在这里选择你想要进行的操作。")
st.sidebar.divider()

# endregion

# region 常量
# streamlit中各页都是相对当前根目录

CURRENT_CWD: Path = Path(__file__).parent.parent
DICT_DIR = CURRENT_CWD / "resource/dictionary"

# endregion

# region 通用状态

THRESHOLD = 20  # 阈值
TIME_LIMIT = 10 * 60  # 10分钟

if "pending_add_words" not in st.session_state:
    st.session_state.pending_add_words = set()

if "pending_del_words" not in st.session_state:
    st.session_state.pending_del_words = set()

if "last_update_time" not in st.session_state:
    st.session_state.last_update_time = time.time()

# endregion

# region 通用函数


@st.cache_data(show_spinner="提取词典...", ttl=60 * 60 * 24)  # 缓存有效期为24小时
def load_word_dict():
    with open(
        DICT_DIR / "word_lists_by_edition_grade.json", "r", encoding="utf-8"
    ) as f:
        return json.load(f)


@st.cache_data(show_spinner="提取简版词典...", ttl=60 * 60 * 24)  # 缓存有效期为24小时
def get_mini_dict():
    db = st.session_state.dbi.db
    collection = db.collection("mini_dict")

    # 从 Firestore 获取数据
    docs = collection.get()

    data = {doc.id: doc.to_dict() for doc in docs}

    return data


def generate_page_words(word_lib_name, num_words, key):
    # 获取选中的单词列表
    words = st.session_state.word_dict[word_lib_name]
    n = min(num_words, len(words))
    # 随机选择单词
    st.session_state[key] = random.sample(words, n)
    name = word_lib_name.split("-", maxsplit=1)[1]
    st.toast(f"当前单词列表名称：{name} 单词数量: {len(st.session_state[key])}")


def add_personal_dictionary(include):
    # 从集合中提取个人词库，添加到word_lists中
    personal_word_list = st.session_state.dbi.find_personal_dictionary()
    if include:
        if len(personal_word_list) > 0:
            st.session_state.word_dict["0-个人词库"] = personal_word_list
    else:
        if "0-个人词库" in st.session_state.word_dict:
            del st.session_state.word_dict["0-个人词库"]


@st.cache_data(ttl=timedelta(hours=24), max_entries=10000, show_spinner="获取单词信息...")
def get_word_info(word):
    return st.session_state.dbi.find_word(word)


@st.cache_data(ttl=timedelta(hours=24), max_entries=10000, show_spinner="获取单词图片网址...")
def select_word_image_urls(word: str):
    # 从 session_state 中的 mini_dict 查找 image_urls
    urls = st.session_state.mini_dict.get(word, {}).get("image_urls", [])
    model = load_vertex_model("gemini-pro-vision")
    if len(urls) == 0:
        images = []
        full_urls = get_word_image_urls(word, st.secrets["SERPER_KEY"])
        for i, url in enumerate(full_urls):
            try:
                image_bytes = load_image_bytes_from_url(url)
                images.append(Image.from_bytes(image_bytes))
            except Exception as e:
                logger.error(f"加载单词{word}第{i+1}张图片时出错:{str(e)}")
                continue
        try:
            # 生成 image_indices
            image_indices = select_best_images_for_word(model, word, images)
        except:
            image_indices = list(range(len(images)))[:4]

        # 检查 indices 是否为列表
        if not isinstance(image_indices, list):
            msg = f"{word} 序号必须是一个列表，但是得到的类型是 {type(image_indices)}"
            logger.error(msg)
            raise TypeError(msg)
        # 检查列表中的每个元素是否都是整数
        if not all(isinstance(i, int) for i in image_indices):
            msg = f"{word} 序号列表中的每个元素都必须是整数，但是得到的类型是 {[type(image_indices[i] for i in image_indices)]}"
            logger.error(msg)
            raise TypeError(msg)

        urls = [full_urls[i] for i in image_indices]
        st.session_state.dbi.update_image_urls(word, urls)

    return urls


def process_pending_words(add_words, del_words):
    # 计算净添加和净删除的单词
    net_add_words = add_words - del_words
    net_del_words = del_words - add_words

    # 提交净添加的单词到数据库
    if net_add_words:
        st.session_state.dbi.add_words_to_personal_dictionary(list(net_add_words))
        add_words -= net_add_words

    # 从数据库中删除净删除的单词
    if net_del_words:
        st.session_state.dbi.remove_words_from_personal_dictionary(list(net_del_words))
        del_words -= net_del_words

    return add_words, del_words


def update_pending_words():
    current_time = time.time()
    if (
        len(st.session_state.pending_add_words) >= THRESHOLD
        or len(st.session_state.pending_del_words) >= THRESHOLD
        or current_time - st.session_state.last_update_time >= TIME_LIMIT
    ):
        (
            st.session_state.pending_add_words,
            st.session_state.pending_del_words,
        ) = process_pending_words(
            st.session_state.pending_add_words, st.session_state.pending_del_words
        )
        st.session_state.last_update_time = current_time


def on_include_cb_change():
    # st.write("on_include_cb_change", st.session_state["include-personal-dictionary"])
    # 更新个人词库
    add_personal_dictionary(st.session_state["include-personal-dictionary"])


def display_word_images(word, container):
    urls = select_word_image_urls(word)
    cols = container.columns(len(urls))
    caption = [f"图片 {i+1}" for i in range(len(urls))]
    for i, col in enumerate(cols):
        col.image(urls[i], use_column_width=True, caption=caption[i])


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

# region 闪卡辅助函数


def reset_flashcard_word():
    # 恢复初始显示状态
    st.session_state.flashcard_words = []
    st.session_state.flashcard_display_state = "全部"
    st.session_state["current_flashcard_word_index"] = -1


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


def view_flash_word(container):
    """
    Display the flashcard word and its information.

    Args:
        container (object): The container to display the flashcard word and information.
        tip_placeholder (object): The placeholder to display the memory tip.

    Returns:
        None
    """

    # if st.session_state.current_flashcard_word_index == -1:
    #     return
    # st.write(st.session_state.current_flashcard_word_index)
    word = st.session_state.flashcard_words[
        st.session_state.current_flashcard_word_index
    ]
    if word not in st.session_state.flashcard_word_info:
        st.session_state.flashcard_word_info[word] = get_word_info(word)

    word_info = st.session_state.flashcard_word_info.get(word, {})
    if not word_info:
        st.error(f"没有该单词：“{word}”的信息。TODO：添加到单词库。")
        st.stop()

    v_word = word
    t_word = ""
    if st.session_state.flashcard_display_state == "中文":
        v_word = ""

    s_word = word.replace("/", " or ")
    if st.session_state.flashcard_display_state != "英文":
        # t_word = word_info["zh-CN"].get("translation", "")
        t_word = st.session_state.mini_dict[s_word].get("translation", "")

    md = template.format(
        word=v_word,
        # cefr=word_info.get("level", ""),
        cefr=st.session_state.mini_dict[s_word].get("level", ""),
        us_written=word_info.get("us_written", ""),
        uk_written=word_info.get("uk_written", ""),
        translation=t_word,
    )

    container.divider()
    container.markdown(md)

    display_word_images(s_word, container)
    view_pos(container, word_info, word)


# endregion

# region 单词拼图状态

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

# endregion

# region 单词拼图辅助函数


def reset_puzzle_word():
    # 恢复初始显示状态
    st.session_state.puzzle_idx = -1
    st.session_state["puzzle_view_word"] = []
    st.session_state["puzzle_test_score"] = {}
    st.session_state.puzzle_answer_value = ""


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
    # 打乱单词字符顺序
    ws = [w for w in word]
    random.shuffle(ws)
    st.session_state.puzzle_view_word = ws
    st.session_state.clicked_character = [False] * len(ws)
    st.session_state.puzzle_answer_value = ""


def view_puzzle_word():
    ws = st.session_state.puzzle_view_word
    n = len(ws)
    cols = st.columns(40)
    button_placeholders = [cols[i].empty() for i in range(n)]
    for i in range(n):
        if button_placeholders[i].button(
            ws[i],
            key=f"btn_{i}",
            disabled=st.session_state.clicked_character[i],
            help="✨ 点击选择字符。",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.puzzle_answer_value += ws[i]
            st.session_state.clicked_character[i] = True
            st.rerun()


def display_puzzle_translation():
    word = st.session_state.puzzle_words[st.session_state.puzzle_idx]
    t_word = st.session_state.mini_dict[word].get("translation", "")
    msg = f"中译文：{t_word}"
    st.markdown(msg)
    st.info("如果字符中包含空格，这可能表示该单词是一个复合词或短语。", icon="ℹ️")


def display_puzzle_definition():
    word = st.session_state.puzzle_words[st.session_state.puzzle_idx]
    definition = get_word_definition(word)
    msg = f"{definition}"
    st.markdown(msg)


# # 前后移动时删除原有文本
# if st.session_state.get("puzzle-prev"):
#     st.session_state["puzzle_answer_value"] = ""
# if st.session_state.get("puzzle-next"):
#     st.session_state["puzzle_answer_value"] = ""


def on_prev_puzzle_btn_click():
    st.session_state["puzzle_idx"] -= 1
    # st.session_state.puzzle_answer_value = ""


def on_next_puzzle_btn_click():
    st.session_state["puzzle_idx"] += 1
    # st.session_state.puzzle_answer_value = ""


def handle_puzzle_input():
    user_input = st.text_input(
        "点击字符按钮或输入您的答案",
        placeholder="点击字符按钮或直接输入您的答案",
        value=st.session_state.puzzle_answer_value,
        key="puzzle_answer",
        label_visibility="collapsed",
    )

    puzzle_score = st.empty()
    sumbit_cols = st.columns(5)

    if sumbit_cols[0].button("重试", help="✨ 恢复初始状态，重新开始。"):
        prepare_puzzle()
        st.rerun()

    if sumbit_cols[1].button("检查", help="✨ 点击按钮，检查您的答案是否正确。"):
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

        score = (
            sum(st.session_state.puzzle_test_score.values())
            / len(st.session_state["puzzle_words"])
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


PICTURE_CATEGORY_MAPS = {
    "animals": "动物",
    "animals-not-mammals": "非哺乳动物",
    "arts-and-crafts": "艺术与手工",
    "at-random": "随机",
    "at-work-and-school": "工作与学校",
    "boats-aircraft-and-trains": "船、飞机与火车",
    "buildings": "建筑物",
    "colours-shapes-and-patterns": "颜色、形状与图案",
    "computers-and-technology": "计算机与技术",
    "cooking-and-kitchen-equipment": "烹饪与厨房设备",
    "food-and-drink": "食物与饮料",
    "fruit-vegetables-herbs-and-spices": "水果、蔬菜、草药与香料",
    "furniture-and-household-equipment": "家具与家用设备",
    "gardens-and-farms": "花园与农场",
    "holidays-vacations": "假期与度假",
    "in-the-past": "过去",
    "in-town-and-shopping": "城镇与购物",
    "music": "音乐",
    "nature-and-weather": "自然与天气",
    "on-the-road": "在路上",
    "plants-trees-and-flowers": "植物、树木与花朵",
    "sports": "运动",
    "taking-care-of-yourself": "照顾自己",
    "the-body": "身体",
    "things-you-wear": "穿着",
    "tools-and-machines": "工具与机器",
    "toys-games-and-entertainment": "玩具、游戏与娱乐",
}


@st.cache_data
def get_pic_categories():
    pic_dir = CURRENT_CWD / "resource/quiz/images"
    return sorted([d.name for d in pic_dir.iterdir() if d.is_dir()])


@st.cache_data(ttl=timedelta(hours=24))
def load_pic_tests(category, num):
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
    return data


def pic_word_test_reset(category, num):
    st.session_state.user_pic_answer = {}
    st.session_state.pic_idx = -1
    data = load_pic_tests(category, num)
    st.session_state["pic_tests"] = data


def on_pic_radio_change(idx):
    # 保存用户答案
    current = st.session_state["pic_options"]
    st.session_state.user_pic_answer[idx] = current


def view_pic_question(container):
    tests = st.session_state.pic_tests
    idx = st.session_state.pic_idx

    question = tests[idx]["question"]
    o_options = tests[idx]["options"]
    options = []
    for f, o in zip("ABC", o_options):
        options.append(f"{f}. {o}")

    image = PIL.Image.open(tests[idx]["image_fp"])  # type: ignore

    user_prev_answer = st.session_state.user_pic_answer.get(idx, options[0])
    user_prev_answer_idx = options.index(user_prev_answer)

    st.divider()
    container.markdown(question)
    container.image(image, caption=tests[idx]["iamge_label"], width=400)  # type: ignore

    container.radio(
        "选项",
        options,
        index=user_prev_answer_idx,
        label_visibility="collapsed",
        key="pic_options",
        on_change=on_pic_radio_change,
        args=(idx,),
    )
    # 🎀
    # 兼顾 改变选项和默认二者的影响
    # on_change 选项变化时赋值
    # 没有赋值时使用 user_prev_answer
    st.session_state.user_pic_answer[idx] = user_prev_answer


def check_pic_answer(container):
    if len(st.session_state.user_pic_answer) == 0:
        st.warning("您尚未答题。")
        st.stop()
    container.empty()
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
        image = PIL.Image.open(tests[idx]["image_fp"])  # type: ignore

        user_answer = st.session_state.user_pic_answer.get(idx, options[0])
        user_answer_idx = options.index(user_answer)
        container.divider()
        container.markdown(question)
        container.image(image, caption=tests[idx]["iamge_label"], width=400)  # type: ignore
        container.radio(
            "选项",
            options,
            index=user_answer_idx,
            disabled=True,
            label_visibility="collapsed",
            key=f"pic_options_{idx}",
        )
        msg = ""
        # container.write(f"显示 idx: {idx} 用户答案：{user_answer.split('.')[1]} 正确答案：{answer}")
        if user_answer.strip().endswith(answer.strip()):
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


# endregion

# region 单词测验辅助函数

# 单词序号

if "word_test_idx" not in st.session_state:
    st.session_state["word_test_idx"] = -1
# 用于测试的单词
if "words_for_test" not in st.session_state:
    st.session_state["words_for_test"] = []
# 单词理解测试题，以单词为键，值为测试题、选项、答案、解释
if "word_tests" not in st.session_state:
    st.session_state["word_tests"] = {}
# 用户答案
if "user_answer" not in st.session_state:
    st.session_state["user_answer"] = {}


def reset_test_words():
    st.session_state.word_test_idx = -1
    st.session_state.word_tests = {}
    st.session_state.user_answer = {}


def on_prev_test_btn_click():
    st.session_state["word_test_idx"] -= 1


def on_next_test_btn_click():
    st.session_state["word_test_idx"] += 1


def check_answer():
    if len(st.session_state.user_answer) == 0:
        st.warning("您尚未答题。")
        st.stop()

    score = 0
    n = len(st.session_state.word_tests)
    for word, test in st.session_state.word_tests.items():
        question = test["问题"]
        options = test["选项"]
        answer = test["答案"]
        explanation = test["解释"]

        user_answer = st.session_state.user_answer.get(word, "")
        user_answer_idx = options.index(user_answer) if user_answer else None
        st.divider()
        st.markdown(question)
        st.radio(
            "选项",
            options,
            # horizontal=True,
            index=user_answer_idx,
            disabled=True,
            label_visibility="collapsed",
            key=f"test-options-{word}",
        )
        msg = ""
        # 用户答案是选项，而提供的标准答案是A、B、C、D
        if user_answer.startswith(answer):
            score += 1
            msg = f"正确答案：{answer} :white_check_mark:"
        else:
            msg = f"正确答案：{answer} :x:"
        st.markdown(msg)
        st.markdown(f"解释：{explanation}")
    percentage = score / n * 100
    if percentage >= 75:
        st.balloons()
    st.divider()
    st.markdown(f":red[得分：{percentage:.0f}%]")
    st.divider()


def view_test_word():
    n = len(st.session_state.words_for_test)
    idx = st.session_state.word_test_idx
    word = st.session_state.words_for_test[idx]
    test = st.session_state.word_tests[word]
    question = test["问题"]
    options = test["选项"]
    user_answer = st.session_state.user_answer.get(word, options[0])
    user_answer_idx = options.index(user_answer)

    st.markdown(question)
    answer = st.radio(
        "选项",
        options,
        # horizontal=True,
        index=user_answer_idx,
        label_visibility="collapsed",
        # key=f"test_options_{idx}",
        # on_change=on_radio_change,
        # args=(
        #     word,
        #     idx,
        # ),
        key="test_options",
    )
    # 保存用户答案
    st.session_state.user_answer[word] = answer


# endregion

# region 会话状态

if "mini_dict" not in st.session_state:
    st.session_state["mini_dict"] = get_mini_dict()

if "word_dict" not in st.session_state:
    # 注意要使用副本
    st.session_state["word_dict"] = load_word_dict().copy()

with open(CURRENT_CWD / "resource/voices.json", "r", encoding="utf-8") as f:
    voice_style_options = json.load(f)

# endregion

# region 闪卡记忆


if menu.endswith("闪卡记忆"):
    # region 词库管理
    # 让用户选择语音风格
    pronunciation = st.sidebar.radio("请选择发音标准", ("美式", "英式"))
    style = "en-US" if pronunciation == "美式" else "en-GB"

    # 固定语音风格
    voice_style = voice_style_options[style][0]
    st.sidebar.info(f"语音风格：{voice_style[0]}({voice_style[1]})")
    st.sidebar.checkbox(
        "是否包含个人词库？",
        key="include-personal-dictionary",
        on_change=on_include_cb_change,
    )
    # 在侧边栏添加一个选项卡让用户选择一个单词列表
    word_lib = st.sidebar.selectbox(
        "词库",
        sorted(list(st.session_state.word_dict.keys())),
        key="flashcard-selected",
        on_change=reset_flashcard_word,
        format_func=lambda x: x.split("-", maxsplit=1)[1],
        help="✨ 选择一个单词列表，用于生成闪卡单词。",
    )

    # 在侧边栏添加一个滑块让用户选择记忆的单词数量
    num_word = st.sidebar.slider(
        "单词数量",
        10,
        50,
        step=5,
        key="flashcard-num-words",
        on_change=reset_flashcard_word,
        help="✨ 请选择计划记忆的单词数量。",
    )
    # endregion

    st.subheader(":book: 闪卡记忆", divider="rainbow", anchor=False)
    st.markdown(
        """✨ 闪卡记忆是一种记忆单词的游戏，其玩法是将单词或短语的中英文对照显示在屏幕上，玩家需要根据提示信息，尽可能多地记住单词或短语的含义。"""
    )

    btn_cols = st.columns(10)
    container = st.container()

    # 创建前后选择的按钮
    display_status_button = btn_cols[0].button(
        ":recycle:",
        key="flashcard-mask",
        help="✨ 点击按钮，可切换显示状态。初始状态显示中英对照。点击按钮，切换为只显示英文。再次点击按钮，切换为只显示中文。",
    )
    btn_cols[1].button(
        ":leftwards_arrow_with_hook:",
        key="flashcard-prev",
        help="✨ 点击按钮，切换到上一个单词。",
        on_click=on_prev_btn_click,
        disabled=st.session_state.current_flashcard_word_index < 0,
    )
    btn_cols[2].button(
        ":arrow_right_hook:",
        key="flashcard-next",
        help="✨ 点击按钮，切换到下一个单词。如果按钮不可用，请点击右侧按钮生成记忆闪卡。",
        on_click=on_next_btn_click,
        disabled=st.session_state.current_flashcard_word_index == -1
        or st.session_state.current_flashcard_word_index
        == len(st.session_state.flashcard_words) - 1,  # type: ignore
    )
    refresh_btn = btn_cols[4].button(
        ":arrows_counterclockwise:",
        key="flashcard-refresh",
        help="✨ 点击按钮，从词库中重新生成记忆闪卡。",
        # on_click=reset_flashcard_word,
        # args=(word_lib, num_word, "flashcard_words"),
    )
    play_btn = btn_cols[3].button(
        ":sound:",
        key="flashcard-play",
        help="✨ 聆听单词发音",
        disabled=st.session_state.current_flashcard_word_index == -1,
    )
    add_btn = btn_cols[5].button(
        ":heavy_plus_sign:",
        key="flashcard-add",
        help="✨ 将当前单词添加到个人词库",
        disabled=st.session_state.current_flashcard_word_index == -1,
    )
    del_btn = btn_cols[6].button(
        ":heavy_minus_sign:",
        key="flashcard-del",
        help="✨ 将当前单词从个人词库中删除",
        disabled=st.session_state.current_flashcard_word_index == -1,
    )

    # 创建按钮
    if display_status_button:
        if st.session_state.flashcard_display_state == "全部":
            st.session_state.flashcard_display_state = "英文"
        elif st.session_state.flashcard_display_state == "英文":
            st.session_state.flashcard_display_state = "中文"
        else:
            st.session_state.flashcard_display_state = "全部"

    if refresh_btn:
        generate_page_words(word_lib, num_word, "flashcard_words")

    if play_btn:
        word = st.session_state.flashcard_words[
            st.session_state.current_flashcard_word_index
        ]
        # 使用会话缓存，避免重复请求
        audio_html = get_audio_html(word, voice_style)
        components.html(audio_html)

    if add_btn:
        word = st.session_state.flashcard_words[
            st.session_state.current_flashcard_word_index
        ]
        st.session_state.pending_add_words.add(word)
        st.toast(f"添加单词：{word} 到个人词库。")

    if del_btn:
        word = st.session_state.flashcard_words[
            st.session_state.current_flashcard_word_index
        ]
        st.session_state.pending_del_words.add(word)
        st.toast(f"从个人词库中删除单词：{word}。")

    # 显示闪卡单词
    if st.session_state["current_flashcard_word_index"] != -1:
        view_flash_word(container)

# endregion

# region 单词拼图

elif menu.endswith("拼图游戏"):
    # region 边栏
    include_cb = st.sidebar.checkbox(
        "是否包含个人词库？",
        key="include-personal-dictionary",
        value=False,
        on_change=on_include_cb_change,
    )
    # 在侧边栏添加一个选项卡让用户选择一个单词列表
    word_lib = st.sidebar.selectbox(
        "词库",
        sorted(list(st.session_state.word_dict.keys())),
        key="puzzle-selected",
        on_change=reset_puzzle_word,
        format_func=lambda x: x.split("-", maxsplit=1)[1],
        help="✨ 选择一个词库，用于生成单词拼图。",
    )

    # 在侧边栏添加一个滑块让用户选择记忆的单词数量
    num_word = st.sidebar.slider(
        "单词数量",
        10,
        50,
        step=5,
        key="puzzle-num-words",
        on_change=reset_puzzle_word,
        help="✨ 单词拼图的数量。",
    )
    # endregion

    st.subheader(":jigsaw: 拼图游戏", divider="rainbow", anchor=False)
    st.markdown(
        "单词拼图是一种记忆单词的游戏，其玩法是将一些字母打乱，玩家需要根据这些字母，结合提示信息拼出正确的单词。它是一种非常有效的学习方式，可以帮助我们提高词汇量、拼写能力、思维能力和解决问题能力。参考：[Cambridge Dictionary](https://dictionary.cambridge.org/)"
    )

    if st.session_state.puzzle_idx != -1:
        update_and_display_progress(
            st.session_state.puzzle_idx + 1,
            len(st.session_state.puzzle_words),
            st.empty(),
        )

    puzzle_cols = st.columns(10)
    puzzle_prev_btn = puzzle_cols[0].button(
        ":leftwards_arrow_with_hook:",
        key="puzzle-prev",
        help="✨ 点击按钮，切换到上一单词拼图。",
        on_click=on_prev_puzzle_btn_click,
        disabled=st.session_state.puzzle_idx < 0,
    )
    puzzle_next_btn = puzzle_cols[1].button(
        ":arrow_right_hook:",
        key="puzzle-next",
        help="✨ 点击按钮，切换到下一单词拼图。",
        on_click=on_next_puzzle_btn_click,
        disabled=len(st.session_state["puzzle_words"])
        and st.session_state.puzzle_idx == len(st.session_state["puzzle_words"]) - 1,
    )
    refresh_btn = puzzle_cols[2].button(
        ":arrows_counterclockwise:",
        key="puzzle-refresh",
        help="✨ 点击按钮后，将从词库中重新抽取单词。",
        on_click=generate_page_words,
        args=(word_lib, num_word, "puzzle_words"),
    )
    puzzle_add_btn = puzzle_cols[3].button(
        ":heavy_plus_sign:",
        key="puzzle-add",
        help="✨ 将当前单词添加到个人词库",
        disabled=st.session_state.puzzle_idx == -1,
    )
    puzzle_del_btn = puzzle_cols[4].button(
        ":heavy_minus_sign:",
        key="puzzle-del",
        help="✨ 将当前单词从个人词库中删除",
        disabled=st.session_state.puzzle_idx == -1,
    )

    # 使用默认值初始化
    if len(st.session_state.puzzle_words) == 0:
        reset_puzzle_word()
        st.rerun()

    if puzzle_prev_btn:
        prepare_puzzle()

    if puzzle_next_btn:
        prepare_puzzle()

    if refresh_btn:
        reset_puzzle_word()

    if st.session_state.puzzle_idx != -1:
        display_puzzle_translation()
        view_puzzle_word()
        handle_puzzle_input()
        word = st.session_state.puzzle_words[st.session_state.puzzle_idx]
        container = st.container()
        display_puzzle_definition()
        display_word_images(
            word,
            container,
        )

    if puzzle_add_btn:
        word = st.session_state.puzzle_words[st.session_state.puzzle_idx]
        st.session_state.pending_add_words.add(word)
        st.toast(f"添加单词：{word} 到个人词库。")

    if puzzle_del_btn:
        word = st.session_state.puzzle_words[st.session_state.puzzle_idx]
        st.session_state.pending_del_words.add(word)
        st.toast(f"从个人词库中删除单词：{word}。")

# endregion

# region 图片测词

elif menu.endswith("看图测词"):
    # region 边栏
    category = st.sidebar.selectbox(
        "请选择图片类别以生成对应的看图测词题目",
        get_pic_categories(),
        format_func=lambda x: PICTURE_CATEGORY_MAPS[x],
        key="pic-category",
    )
    pic_num = st.sidebar.number_input(
        "请选择您希望生成的看图测词题目的数量",
        1,
        20,
        value=10,
        step=1,
        key="pic-num",
    )
    # endregion
    st.subheader(":frame_with_picture: 看图测词", divider="rainbow", anchor=False)
    st.markdown(
        """看图测词是一种记忆单词的方法，它通过提供图片，让用户根据图片内容猜测对应的单词。数据来源：[Cambridge Dictionary](https://dictionary.cambridge.org/)

请注意，专业领域的单词可能较为生僻，因此这种方法可能具有一定的难度。如果你对某个领域不熟悉，可能需要投入更多的精力。因此，我们建议你只在你感兴趣或熟悉的领域尝试这种方法。
        """
    )

    if len(st.session_state.pic_tests) == 0:
        pic_word_test_reset(category, pic_num)
        st.rerun()

    if st.session_state.pic_idx != -1:
        update_and_display_progress(
            st.session_state.pic_idx + 1, len(st.session_state.pic_tests), st.empty()
        )

    pic_word_test_btn_cols = st.columns(10)

    # 创建按钮
    prev_pic_btn = pic_word_test_btn_cols[0].button(
        ":leftwards_arrow_with_hook:",
        help="✨ 点击按钮，切换到上一题。",
        on_click=on_prev_pic_btn_click,
        key="prev-pic",
        disabled=st.session_state.pic_idx < 0,
    )

    next_pic_btn = pic_word_test_btn_cols[1].button(
        ":arrow_right_hook:",
        help="✨ 点击按钮，切换到下一题。",
        on_click=on_next_pic_btn_click,
        key="next-pic",
        disabled=st.session_state.pic_idx == pic_num - 1,
    )
    # 答题即可提交检查
    sumbit_pic_btn = pic_word_test_btn_cols[2].button(
        ":mag:",
        key="submit-pic",
        disabled=len(st.session_state.pic_tests) == 0
        or len(st.session_state.user_pic_answer) == 0,
        help="✨ 只有在完成至少一道测试题后，才能点击按钮查看测验得分。",
    )
    refresh_btn = pic_word_test_btn_cols[3].button(
        ":arrows_counterclockwise:",
        key="refresh-pic",
        help="✨ 点击按钮，重新开始看图测词。",
        on_click=pic_word_test_reset,
        args=(category, pic_num),
    )

    container = st.container()
    if sumbit_pic_btn:
        if len(st.session_state.user_pic_answer) != len(st.session_state.pic_tests):
            st.warning("您尚未完成全部测试题目。")
        check_pic_answer(container)
    elif st.session_state.pic_idx != -1:
        view_pic_question(container)


# endregion

# region 词义理解

elif menu.endswith("词义理解"):
    # region 边栏
    level = st.sidebar.selectbox(
        "CEFR分级",
        CEFR_LEVEL_MAPS.keys(),
        key="test-word-level",
    )
    include_cb = st.sidebar.checkbox(
        "是否包含个人词库？",
        key="include-personal-dictionary",
        value=False,
        on_change=on_include_cb_change,
    )
    # 在侧边栏添加一个选项卡让用户选择一个单词列表
    word_lib = st.sidebar.selectbox(
        "词库",
        sorted(list(st.session_state.word_dict.keys())),
        key="test-word-selected",
        on_change=reset_test_words,
        format_func=lambda x: x.split("-", maxsplit=1)[1],
        help="✨ 选择一个单词列表，用于生成单词词义理解测试题。",
    )
    test_num = st.sidebar.number_input(
        "试题数量",
        1,
        20,
        value=10,
        step=1,
        key="test-word-num",
        on_change=reset_test_words,
    )
    # endregion

    st.subheader(":pencil: 英语单词理解测试", divider="rainbow", anchor=False)
    st.markdown("""英语单词理解测试是一种测试方式，它提供一个英语单词和四个可能的含义，要求你选择唯一正确的含义。""")

    if st.session_state.word_test_idx != -1:
        update_and_display_progress(
            st.session_state.word_test_idx + 1,
            len(st.session_state.words_for_test),
            st.empty(),
            message=st.session_state.words_for_test[st.session_state.word_test_idx],
        )

    test_btns = st.columns(10)

    prev_test_btn = test_btns[0].button(
        ":leftwards_arrow_with_hook:",
        key="prev-test-word",
        help="✨ 点击按钮，切换到上一题。",
        on_click=on_prev_test_btn_click,
        disabled=st.session_state.word_test_idx < 0,
    )
    next_test_btn = test_btns[1].button(
        ":arrow_right_hook:",
        key="next-test-word",
        help="✨ 点击按钮，切换到下一题。",
        on_click=on_next_test_btn_click,
        disabled=st.session_state.word_test_idx
        == len(st.session_state.words_for_test) - 1,
    )

    # 答题即可提交检查
    sumbit_test_btn = test_btns[2].button(
        ":mag:",
        key="submit-test-word",
        disabled=st.session_state.word_test_idx == -1
        or len(st.session_state.user_answer) == 0,
        help="✨ 至少完成一道测试题后，才可点击按钮，显示测验得分。",
    )

    refresh_btn = test_btns[3].button(
        ":arrows_counterclockwise:",
        key="test-word-refresh",
        help="✨ 点击按钮后，将从词库中重新抽取单词。",
        on_click=generate_page_words,
        args=(word_lib, test_num, "words_for_test"),
    )

    if prev_test_btn:
        idx = st.session_state.word_test_idx
        word = st.session_state.words_for_test[idx]
        if word not in st.session_state.word_tests:
            with st.spinner("AI🤖正在生成单词理解测试题，请稍候..."):
                model = load_vertex_model("gemini-pro")
                st.session_state.word_tests[word] = generate_word_test(
                    model, word, level
                )
        view_test_word()

    if next_test_btn:
        idx = st.session_state.word_test_idx
        word = st.session_state.words_for_test[idx]
        if word not in st.session_state.word_tests:
            with st.spinner("AI🤖正在生成单词理解测试题，请稍候..."):
                model = load_vertex_model("gemini-pro")
                st.session_state.word_tests[word] = generate_word_test(
                    model, word, level
                )
        view_test_word()

    if sumbit_test_btn:
        if len(st.session_state.user_answer) != len(st.session_state.word_tests):
            st.warning("您尚未完成测试。")
        check_answer()

    if refresh_btn:
        reset_test_words()
        st.rerun()

# endregion


# # region 个人词库辅助

# add_my_word_lib_column_config = {
#     "添加": st.column_config.CheckboxColumn(
#         "添加",
#         help="✨ 点击复选框，选中单词添加到个人词库",
#         width="small",
#         required=True,
#     )
# }

# del_my_word_lib_column_config = {
#     "删除": st.column_config.CheckboxColumn(
#         "删除",
#         help="✨ 点击复选框，从个人词库中删除该单词",
#         width="small",
#         required=True,
#     )
# }


# def gen_word_lib():
#     words = st.session_state.word_dict[st.session_state["selected_list"]]
#     for word in words:
#         if word not in st.session_state.flashcard_word_info:
#             st.session_state.flashcard_word_info[word] = get_word_info(word)
#     data = []
#     for w in words:
#         info = st.session_state.flashcard_word_info[w]
#         data.append(
#             {
#                 "单词": w,
#                 "CEFR最低分级": info.get("level", "") if info else "",
#                 "翻译": info["zh-CN"].get("translation", "") if info else "",
#                 "添加": False,
#             }
#         )
#     return pd.DataFrame.from_records(data)


# def gen_my_word_lib():
#     my_words = st.session_state.dbi.find_personal_dictionary()
#     # st.write("个人词库：", my_words)
#     for word in my_words:
#         if word not in st.session_state.flashcard_word_info:
#             st.session_state.flashcard_word_info[word] = get_word_info(word)
#     data = []
#     for w in my_words:
#         data.append(
#             {
#                 "单词": w,
#                 "CEFR最低分级": st.session_state.flashcard_word_info[w].get("level", ""),
#                 "翻译": st.session_state.flashcard_word_info[w]["zh-CN"].get(
#                     "translation", ""
#                 ),
#                 "删除": False,
#             }
#         )
#     return pd.DataFrame.from_records(data)


# EDITABLE_COLS: list[str] = [
#     "删除",
#     "添加",
# ]

# # endregion

# # region 个人词库

# with tabs[tab_items.index(":books: 个人词库")]:
#     lib_cols = st.columns(2)
#     view_selected_list = ""
#     if st.session_state["selected_list"] is not None:
#         view_selected_list = st.session_state["selected_list"].split("-", maxsplit=1)[1]
#     lib_cols[0].markdown(f"#### 基础词库({view_selected_list})")
#     placeholder = lib_cols[0].empty()
#     lib_cols[1].markdown("#### 个人词库")
#     mywords_placeholder = lib_cols[1].empty()
#     add_lib_btn = lib_cols[0].button(
#         ":heavy_plus_sign:", key="add-lib-btn", help="✨ 点击按钮，将'基础词库'中已选单词添加到个人词库。"
#     )
#     del_lib_btn = lib_cols[1].button(
#         ":heavy_minus_sign:", key="del-lib-btn", help="✨ 点击按钮，将已选单词从'个人词库'中删除。"
#     )
#     df = gen_word_lib()
#     edited_df = placeholder.data_editor(
#         df,
#         key="word_lib",
#         hide_index=True,
#         column_config=add_my_word_lib_column_config,
#         height=500,
#         disabled=[col for col in df.columns if col not in EDITABLE_COLS],
#     )
#     if add_lib_btn and st.session_state.get("word_lib", None):
#         word_lib = st.session_state["word_lib"]
#         edited_rows = word_lib["edited_rows"]
#         # st.write("编辑的行：", edited_rows)
#         for idx, d in edited_rows.items():
#             word = df.iloc[idx]["单词"]  # type: ignore
#             if d["添加"]:
#                 st.session_state.dbi.add_words_to_personal_dictionary(word)
#                 st.toast(f"已添加到个人词库中：{word}。")

#         word_lib["edited_rows"] = {}

#     my_word_df = gen_my_word_lib()
#     mywords_placeholder.data_editor(
#         my_word_df,
#         key="my_word_lib",
#         hide_index=True,
#         column_config=del_my_word_lib_column_config,
#         height=500,
#         disabled=[col for col in df.columns if col not in EDITABLE_COLS],
#     )

#     if del_lib_btn and st.session_state.get("my_word_lib", None):
#         my_word_lib = st.session_state["my_word_lib"]
#         my_word_edited_rows = my_word_lib["edited_rows"]
#         # st.write("编辑的行：", edited_rows)
#         for idx, d in my_word_edited_rows.items():
#             word = my_word_df.iloc[idx]["单词"]  # type: ignore
#             if d["删除"]:
#                 st.session_state.dbi.remove_words_from_personal_dictionary(word)
#                 st.toast(f"已从个人词库中删除：{word}。")
#         st.rerun()

# # endregion


# 更新待处理的单词
update_pending_words()
