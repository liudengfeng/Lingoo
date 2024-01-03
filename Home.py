import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from PIL import Image

from mypylib.auth_utils import is_valid_phone_number
from mypylib.azure_speech import speech_synthesis_get_available_voices
from mypylib.constants import LANGUAGES
from mypylib.db_model import PaymentStatus
from mypylib.db_interface import DbInterface
from mypylib.st_helper import check_and_force_logout, get_firestore_client

CURRENT_CWD: Path = Path(__file__).parent
LOGO_DIR: Path = CURRENT_CWD / "resource/logo"

VOICES_FP = CURRENT_CWD / "resource/voices.json"

st.set_page_config(
    page_title="主页",
    page_icon="🏠",
    layout="wide",
)

if "dbi" not in st.session_state:
    st.session_state["dbi"] = DbInterface(get_firestore_client())

if "user_info" not in st.session_state:
    st.session_state["user_info"] = {}


need_update = False
# 如果文件不存在，或者文件的最后修改时间距离当前时间超过120天
if not os.path.exists(VOICES_FP):
    need_update = True
else:
    # 获取当前时间
    now = time.time()
    # 获取文件的最后修改时间
    mtime = os.path.getmtime(VOICES_FP)
    if now - mtime >= 120 * 24 * 60 * 60:
        need_update = True

if need_update:
    res = {}
    with st.spinner("正在更新语音列表，请稍后..."):
        for lan in LANGUAGES:
            res[lan] = speech_synthesis_get_available_voices(
                lan,
                st.secrets["Microsoft"]["SPEECH_KEY"],
                st.secrets["Microsoft"]["SPEECH_REGION"],
            )
        # 将数据存储为 JSON 格式
        with open(VOICES_FP, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)


s_cols = st.sidebar.columns(3)
login_btn = s_cols[0].button(
    label="登录" if not st.session_state["user_info"] else ":bust_in_silhouette: 已登录",
    type="primary" if not st.session_state["user_info"] else "secondary",
    disabled=len(st.session_state["user_info"]) >= 1,
)
logout_btn = s_cols[1].button("退出", help="✨ 在公共场所使用本产品时，请在离开前退出登录，以保护您的隐私和安全。")

# 获取当前的日期和时间
current_datetime = datetime.now(timezone.utc)
extend_time_btn_disabled = False

sidebar_status = st.sidebar.empty()

# 在页面加载时检查是否有需要强制退出的登录会话
# check_and_force_logout(sidebar_status)

# if len(st.session_state["user_info"]) >= 1:
#     # 获取用户的数据
#     user_data = st.session_state.dbi.users.find_one(
#         {"phone_number": st.session_state["user_info"]["phone_number"]}
#     )
#     # 查询在服务期内，处于服务状态的支付记录
#     payment_record = st.session_state.dbi.payments.find_one(
#         {
#             "phone_number": st.session_state["user_info"]["phone_number"],
#             "status": PaymentStatus.IN_SERVICE,
#         }
#     )
#     # 检查用户是否已经领取 TODO:使用 user tz
#     if (current_datetime.hour + 8) < 6 or 20 <= (current_datetime.hour + 8):
#         extend_time_btn_disabled = False
#     else:
#         extend_time_btn_disabled = True

#     if user_data:
#         # 获取用户的最后领取日期
#         last_received_date = user_data.get("last_received_date")
#         # 检查 last_received_date 是否存在并且是 datetime 对象
#         if last_received_date and isinstance(last_received_date, datetime):
#             if current_datetime.date() == last_received_date.date():
#                 extend_time_btn_disabled = True

#     extend_time_btn = s_cols[2].button(
#         "免费🎁",
#         disabled=extend_time_btn_disabled,
#         help="✨ 付费用户每天上午6点至下午8点打卡。奖励1小时。",
#     )

#     if extend_time_btn and payment_record:
#         # 获取用户的到期时间
#         expiry_time = payment_record.get("expiry_time", datetime.now(timezone.utc))

#         # 将到期时间转换为时间戳
#         expiry_timestamp = expiry_time.timestamp()

#         # 增加1小时的秒数
#         expiry_timestamp += 60 * 60

#         # 将时间戳转回日期
#         new_expiry_time = datetime.fromtimestamp(expiry_timestamp)

#         # 更新用户的到期时间
#         st.session_state.dbi.payments.update_one(
#             {"phone_number": st.session_state["user_info"]["phone_number"]},
#             {"$set": {"expiry_time": new_expiry_time}},
#         )

#         # 更新用户的最后领取日期
#         st.session_state.dbi.users.update_one(
#             {"phone_number": st.session_state["user_info"]["phone_number"]},
#             {"$set": {"last_received_date": current_datetime}},
#         )
#         # 重新刷新
#         st.rerun()

#     if user_data and payment_record:
#         # 计算剩余的时间
#         expiry_time = payment_record.get("expiry_time", datetime.now(timezone.utc))
#         remaining_time = (
#             expiry_time.timestamp() - datetime.now(timezone.utc).timestamp()
#         )
#         remaining_days = remaining_time // (24 * 60 * 60)
#         remaining_hours = (remaining_time - remaining_days * 24 * 60 * 60) // 3600
#         remaining_minutes = (
#             remaining_time - remaining_days * 24 * 60 * 60 - remaining_hours * 3600
#         ) // 60
#         sidebar_status.info(
#             f"剩余{remaining_days:.0f}天{remaining_hours:.0f}小时{remaining_minutes:.0f}分钟到期"
#         )

if len(st.session_state["user_info"]) == 0:
    if st.session_state.user_info and st.session_state.dbi.cache.get(
        st.session_state.user_info["phone_number"]
    ):
        sidebar_status.success(f"您已登录，{st.session_state.user_info['display_name']} 您好！")
    with st.sidebar.form(key="login_form", clear_on_submit=True):
        phone_number = st.text_input(
            "手机号码",
            type="password",
            key="phone_number",
            help="✨ 请输入手机号码",
            placeholder="输入手机号码",
        )
        password = st.text_input(
            "密码",
            type="password",
            key="password",
            help="✨ 输入个人登录密码",
            placeholder="输入个人登录密码",
        )
        sub_btn = st.form_submit_button(label="确认")
        if sub_btn:
            if not is_valid_phone_number(phone_number):
                sidebar_status.error(f"请输入有效的手机号码。您输入的号码是：{phone_number}")
                st.stop()
            else:
                info = st.session_state.dbi.login(
                    phone_number=phone_number, password=password
                )
                if info.get("status", "") == "success":
                    display_name = info["display_name"]
                    sidebar_status.success(info["message"])
                    st.session_state["user_info"] = {}
                    st.session_state["user_info"]["phone_number"] = phone_number
                    st.session_state["user_info"]["user_role"] = info["user_role"]
                    st.session_state["user_info"]["session_id"] = info["session_id"]
                    st.session_state["user_info"]["display_name"] = display_name
                    time.sleep(2)
                    st.rerun()
                elif info["status"] == "warning":
                    sidebar_status.warning(info["message"])
                    st.stop()
                else:
                    sidebar_status.error(info["message"])
                    st.stop()


col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
## `LinGoo`[英语速学]

**LinGoo**的功能包括：

**:books: 记忆单词**：通过AI智能推荐和游戏化学习，让你轻松记住单词。

**🎤 口语练习**：与AI对话，提高口语能力。

**🎧 听力练习**：提高听力能力。

**:book: 阅读理解**：阅读原汁原味的英语文章，提升阅读水平。

**✍️ 写作练习**：根据提示写出流利的英语句子。

**🗣️ 能力评估**：使用最新微软语言对话能力评估技术，帮助你纠正错误发音，提升对话能力。

**只需要一副麦克风、耳机，就可以随时随地学习英语。**                
        """
    )


logo_image = Image.open(LOGO_DIR / "logo.png")
with col2:
    st.image(logo_image, width=320)
st.divider()

step_cols = st.columns(5)
with step_cols[1]:
    st.link_button(":bust_in_silhouette: 注册用户", "注册订阅#用户注册")

with step_cols[2]:
    st.link_button(":package: 订阅套餐", "注册订阅#订阅套餐")

with step_cols[3]:
    st.link_button(":key: 登录使用", "#")

log_cols = st.columns(3)
welcome_image = Image.open(LOGO_DIR / "welcome-1.jpg")
with log_cols[1]:
    st.image(welcome_image, use_column_width=True)


st.markdown(
    """\
欢迎来到`LinGoo` [英语速学] ，你的英语学习伙伴！

**LinGoo**是一款功能强大的英语学习app，它使用最新AI技术和微软发音评估技术，可以帮助你快速提升英语水平。

LinGoo，让你学好英语，so easy！
""",
    unsafe_allow_html=True,
)

if len(st.session_state["user_info"]) >= 1:
    if logout_btn:
        st.session_state.dbi.logout(st.session_state.user_info)
        st.session_state["user_info"] = {}
        sidebar_status.success("已退出登录")
        st.rerun()
