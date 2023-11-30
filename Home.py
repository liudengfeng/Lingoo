import json
import os
import random
import time
from pathlib import Path

import streamlit as st
from PIL import Image

from mypylib.auth_utils import is_valid_email, is_valid_phone_number
from mypylib.authenticate import DbInterface
from mypylib.azure_speech import speech_synthesis_get_available_voices
from mypylib.constants import LANGUAGES

current_cwd: Path = Path(__file__).parent
logo_dir: Path = current_cwd / "resource/logo"

voices_fp = current_cwd / "resource/voices.json"

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "is_login" not in st.session_state:
    st.session_state["is_login"] = False
if "dbi" not in st.session_state:
    st.session_state["dbi"] = DbInterface()

st.set_page_config(
    page_title="主页",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

need_update = False
# 如果文件不存在，或者文件的最后修改时间距离当前时间超过15天
if not os.path.exists(voices_fp):
    need_update = True
else:
    # 获取当前时间
    now = time.time()
    # 获取文件的最后修改时间
    mtime = os.path.getmtime(voices_fp)
    if now - mtime >= 30 * 24 * 60 * 60:
        need_update = True

if need_update:
    res = {}
    with st.spinner("正在更新语音列表，请稍后..."):
        for lan in LANGUAGES:
            res[lan] = speech_synthesis_get_available_voices(
                lan,
                st.secrets["Microsoft"]["SPEECH_KEY"],
                st.secrets["Microsoft"]["SPEECH_SERVICE_REGION"],
            )
        # 将数据存储为 JSON 格式
        with open(voices_fp, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)


s_cols = st.sidebar.columns(2)
login_btn = s_cols[0].button(
    label="登录" if not st.session_state["is_login"] else "👤 已登录",
    type="primary" if st.session_state["is_login"] else "secondary",
    disabled=st.session_state["is_login"],
)
logout_btn = s_cols[1].button("退出", help="在公共场所使用本产品时，请在离开前退出登录，以保护您的隐私和安全。")
status = st.sidebar.empty()


if not st.session_state["is_login"]:
    # with cols[1].form(key="login_form", clear_on_submit=True):
    with st.sidebar.form(key="login_form", clear_on_submit=True):
        identifier = st.text_input(
            "标识符",
            type="password",
            key="identifier",
            help="请输入手机号码",
            placeholder="使用手机号码登录",
        )
        password = st.text_input(
            "密码",
            type="password",
            key="password",
            help="输入个人登录密码",
            placeholder="个人登录密码",
        )
        sub_btn = st.form_submit_button(label="确定")
        if st.session_state.user_id and st.session_state.dbi.cache.get(
            st.session_state.user_id
        ):
            status.success(f"您已登录，{st.session_state.user_id} 您好！")
        if sub_btn:
            phone_number = None
            if identifier:
                st.session_state["user_id"] = identifier
                if is_valid_phone_number(identifier):
                    phone_number = identifier
                else:
                    status.error("请输入有效的手机号码")
                    st.stop()
                msg = st.session_state.dbi.login(
                    phone_number=phone_number, password=password
                )
                if msg == "Login successful":
                    st.session_state["is_login"] = True
                    status.success(f"登录成功，{identifier} 您好！")
                    # st.rerun()
                elif msg == "您已登录":
                    status.success("您已登录")
                else:
                    status.error(msg)
            else:
                status.error("请输入有效的手机号码")
                st.stop()

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
## `LinGoo`[英语速学]

**LinGoo**的功能包括：

**📚 记忆单词**：通过AI智能推荐和游戏化学习，让你轻松记住单词。

**🎤 口语练习**：与AI对话，提高口语能力。

**🎧 听力练习**：提高听力能力。

**📖 阅读理解**：阅读原汁原味的英语文章，提升阅读水平。

**✍️ 写作练习**：根据提示写出流利的英语句子。

**🗣️ 能力评估**：使用最新微软语言对话能力评估技术，帮助你纠正错误发音，提升对话能力。

**只需要一副麦克风、耳机，就可以随时随地学习英语。**                
        """
    )


logo_image = Image.open(logo_dir / "logo.png")
with col2:
    st.image(logo_image, width=320)
st.divider()

log_cols = st.columns(5)
welcome_image = Image.open(logo_dir / "welcome-1.jpg")

with log_cols[1]:
    st.markdown("""<a href="用户管理" target="_self">点击注册</a>""", unsafe_allow_html=True)
    st.markdown("""<a href="用户管理" target="_self">点击付费</a>""", unsafe_allow_html=True)

with log_cols[2]:
    st.image(welcome_image, width=200)


st.markdown(
    """\
欢迎来到`LinGoo`[英语速学]，你的英语学习伙伴！

**LinGoo**是一款功能强大的英语学习app，它使用最新AI技术和微软发音评估技术，可以帮助你快速提升英语水平。

LinGo，让你学好英语，so easy！
""",
    unsafe_allow_html=True,
)


# cols = st.columns(5)
# with cols[2]:
#     welcome_image = Image.open(logo_dir / "welcome-2.jpg")
#     st.image(welcome_image, width=100)
#     st.markdown("[注册使用](用户管理)")


if logout_btn:
    st.session_state.dbi.logout(st.session_state.user_id)
    st.session_state["is_login"] = False
    st.session_state["user_id"] = None
    status.success("已退出登录")
