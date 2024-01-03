import time
import uuid
from pathlib import Path

import pytz
import streamlit as st
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

# from cryptography.fernet import Fernet
from PIL import Image

from mypylib.auth_utils import is_valid_email
from mypylib.constants import PROVINCES, CEFR_LEVEL_MAPS
from mypylib.db_interface import DbInterface
from mypylib.db_model import User
from mypylib.st_helper import check_and_force_logout, get_firestore_client

CURRENT_CWD: Path = Path(__file__).parent.parent
FEEDBACK_DIR = CURRENT_CWD / "resource" / "feedback"

# 创建 Fernet 实例【必须将key转换为bytes类型】
# fernet = Fernet(st.secrets["FERNET_KEY"].encode())

st.set_page_config(
    page_title="用户管理",
    page_icon=":busts_in_silhouette:",
    layout="wide",
)


if "dbi" not in st.session_state:
    st.session_state["dbi"] = DbInterface(get_firestore_client())

if not st.session_state.dbi.is_logged_in():
    st.error("您的账号尚未激活，无法使用本页。")
    st.stop()

# region 侧边栏

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(sidebar_status)


# endregion

emojis = [
    ":arrows_counterclockwise:",
    ":key:",
    ":bar_chart:",
    ":memo:",
]
item_names = ["更新信息", "重置密码", "统计报表", "问题反馈"]
items = [f"{e} {n}" for e, n in zip(emojis, item_names)]
tabs = st.tabs(items)


# region 创建更新信息页面

with tabs[items.index(":arrows_counterclockwise: 更新信息")]:
    st.subheader(":arrows_counterclockwise: 更新个人信息")
    CEFR = list(CEFR_LEVEL_MAPS.keys())
    COUNTRIES = ["中国"]
    user = st.session_state.dbi.get_user()
    # user.set_secret_key(st.secrets["FERNET_KEY"])

    with st.form(key="update_form"):
        col1, col2 = st.columns(2)
        col1.text_input(
            "手机号码",
            key="phone_number-3",
            help="✨ 请输入有效手机号码",
            value=user.phone_number,
            disabled=True,
        )
        email = col2.text_input(
            "邮箱", key="email-3", help="✨ 请输入您常用的电子邮件地址", value=user.email
        )
        real_name = col1.text_input(
            "真实姓名",
            key="real_name-3",
            help="✨ 请输入您在成绩册上的姓名。",
            value=user.real_name,
        )
        display_name = col2.text_input(
            "显示名称", key="display_name-3", help="✨ 请输入您的登录显示名称。", value=user.display_name
        )
        current_level = col1.selectbox(
            "当前英语水平",
            CEFR,
            index=CEFR.index(user.current_level),
            key="current_level-3",
            help="✨ 请选择您当前的英语水平。如果您不了解如何分级，请参阅屏幕下方关于CEFR分级的说明。",
        )
        target_level = col2.selectbox(
            "期望达到的英语水平",
            CEFR,
            index=CEFR.index(user.target_level),
            key="target_level-3",
            help="✨ 请选择您期望达到的英语水平。如果您不了解如何分级，请参阅屏幕下方关于CEFR分级的说明。",
        )
        country = col1.selectbox(
            "所在国家",
            COUNTRIES,
            index=COUNTRIES.index(user.country),
            key="country-3",
        )
        province = col2.selectbox(
            "所在省份", PROVINCES, index=PROVINCES.index(user.province), key="province-3"
        )
        tz = col1.selectbox(
            "所在时区",
            pytz.common_timezones,
            index=pytz.common_timezones.index(user.timezone),
            key="timezone-3",
            help="✨ 请选择您当前所在的时区。如果您在中国，请使用默认值。",
        )
        status = st.empty()
        if st.form_submit_button(label="确认"):
            update_fields = {}
            if email:
                update_fields["email"] = email
            if real_name:
                update_fields["real_name"] = real_name
            if display_name:
                update_fields["display_name"] = display_name
            if current_level:
                update_fields["current_level"] = current_level
            if target_level:
                update_fields["target_level"] = target_level
            if country:
                update_fields["country"] = country
            if province:
                update_fields["province"] = province
            if tz:
                update_fields["timezone"] = tz

            if not update_fields:
                status.error("您没有修改任何信息")
                st.stop()

            try:
                st.session_state.dbi.update_user(user.phone_number, update_fields)
                st.toast(f"成功更新用户：{user.phone_number}的信息！")
                st.rerun()
            except Exception as e:
                st.error(e)
                raise e

# endregion

# region 创建重置密码页面

with tabs[items.index(":key: 重置密码")]:
    st.subheader(":key: 重置密码")
    user = st.session_state.dbi.get_user(st.session_state.user_info["phone_number"])
    # user = User.from_doc(user_doc)
    with st.form(key="secret_form", clear_on_submit=True):
        password_reg = st.text_input(
            "密码",
            type="password",
            key="password_reg-4",
            help="✨ 密码长度至少为8位",
            placeholder="请输入密码，至少为8位",
        )
        password_reg_repeat = st.text_input(
            "密码",
            type="password",
            key="password_reg_repeat-4",
            help="✨ 请再次输入密码",
            placeholder="请再次输入密码以确认",
        )
        status = st.empty()
        if st.form_submit_button(label="确认"):
            if password_reg != password_reg_repeat:
                status.error("两次输入的密码不一致")
                st.stop()
            user.password = password_reg
            # 必须加密
            user.hash_password()
            st.session_state.dbi.update_user(
                st.session_state.user_info["phone_number"],
                {
                    "password": user.password,
                },
            )
            st.toast("密码重置成功！")
            st.session_state.dbi.logout()
            st.info("请使用新密码重新登录。", icon="ℹ️")

# endregion

# region 创建统计页面

with tabs[items.index(":bar_chart: 统计报表")]:
    st.subheader(":bar_chart: 统计报表")

# endregion

# region 创建反馈页面


with tabs[items.index(":memo: 问题反馈")]:
    with st.form(key="feedback_form"):
        title = st.text_input("标题", key="title", help="✨ 请输入标题")
        content = st.text_area("问题描述", key="content", help="✨ 请输入内容")
        uploaded_file = st.file_uploader(
            ":file_folder: 上传截屏视频",
            type=["webm"],
            help="✨ 请按<<如何录制截屏视频>>指引，录制视频反馈给管理员。",
        )
        if st.form_submit_button(label="提交"):
            container_name = "feedback"
            connect_str = st.secrets["Microsoft"]["AZURE_STORAGE_CONNECTION_STRING"]
            blob_service_client = BlobServiceClient.from_connection_string(connect_str)
            container_client = blob_service_client.get_container_client(container_name)
            try:
                container_client.get_container_properties()
                # print("Container exists.")
            except ResourceNotFoundError:
                container_client = blob_service_client.create_container(container_name)
                # print("Container does not exist.")

            # 将标题和内容存储为文本文件
            text_data = f"用户：{st.session_state.user_info['phone_number']}\n标题: {title}\n内容: {content}"

            blob_name = str(uuid.uuid4())
            text_blob_client = blob_service_client.get_blob_client(
                container_name, f"{blob_name}.txt"
            )
            text_blob_client.upload_blob(text_data, overwrite=True)

            # 如果用户上传了视频文件，将视频文件存储在blob中
            if uploaded_file is not None:
                video_blob_name = f"{blob_name}.webm"
                video_blob_client = blob_service_client.get_blob_client(
                    container_name, video_blob_name
                )
                # To read file as bytes:
                bytes_data = uploaded_file.getvalue()
                video_blob_client.upload_blob(bytes_data, overwrite=True)

            st.toast("提交成功！")

    with st.expander("如何录制截屏视频..."):
        st.markdown(
            """#### 如何录制截屏视频
您可以直接从您的应用程序轻松进行屏幕录制！最新版本的 Chrome、Edge 和 Firefox 支持屏幕录制。确保您的浏览器是最新的兼容性。根据您当前的设置，您可能需要授予浏览器录制屏幕或使用麦克风（录制画外音）的权限。
1. 请从应用右上角打开应用菜单(浏览器地址栏下方，屏幕右上角)。
    """
        )
        image_1 = Image.open(FEEDBACK_DIR / "step-1.png")
        st.image(image_1, width=200)

        st.markdown(
            """2. 单击"Record a screencast"。
    3. 如果要通过麦克风录制音频，请选中"Also record audio"。
    """
        )
        image_2 = Image.open(FEEDBACK_DIR / "step-2.png")
        st.image(image_2, width=400)

        st.markdown(
            """4. 单击"Start recording!"。(操作系统可能会提示您允许浏览器录制屏幕或使用麦克风。)
    5. 从列出的选项中选择要录制的选项卡、窗口或监视器。界面会因您的浏览器而异。
    """
        )
        image_3 = Image.open(FEEDBACK_DIR / "step-3.png")
        st.image(image_3, width=400)

        st.markdown(
            """6. 单击"共享"。
    """
        )
        image_4 = Image.open(FEEDBACK_DIR / "step-4.png")
        st.image(image_4, width=400)

        st.markdown(
            """
7. 录制时，您将在应用程序的选项卡和应用程序菜单图标上看到一个红色圆圈。如果您想取消录制，请单击应用程序底部的“停止共享”。
    """
        )
        image_5 = Image.open(FEEDBACK_DIR / "step-5.png")
        st.image(image_5, width=400)

        st.markdown(
            """
8. 完成录制后，按键盘上的“Esc”或单击应用程序菜单中的“停止录制”。
    """
        )
        image_6 = Image.open(FEEDBACK_DIR / "step-6.png")
        st.image(image_6, width=400)

        st.markdown(
            """
9. 按照浏览器的说明保存您的录音。您保存的录音将在浏览器保存下载内容的地方可用。
    """
        )

# endregion

# with st.expander("操作提示..."):
#     st.markdown(
#         """#### 操作提示
# - 登录：
#     - 点击选项卡中的“登录”选项；
#     - 输入用手机号码或个人邮箱、密码；
#     - 点击“登录”按钮。
#     - 如果您已经付费，请使用以下方式直接登录：
#         1. 在“登录”选项，输入您的手机号码或邮箱。
#         2. 输入默认密码：12345678。
#         3. 点击“登录”。
#         登录成功后，您可以在“更新”选项修改个人信息。
# - 注册：
#     - 点击选项卡中的“注册”选项；
#     - 填写注册信息；
#     - 点击“注册”按钮。
# - 缴费：
#     - 点击选项卡中的“缴费”选项；
#     - 选择缴费方式；
#     - 扫码完成支付。
# - 更新个人信息：
#     - 点击选项卡中的“更新”选项；
#     - 修改个人信息；
#     - 点击“保存”按钮。
# - 查询学习记录：
#     - 点击选项卡中的“统计”选项；
#     - 选择查询条件；
#     - 点击“查询”按钮。
# - 反馈问题：
#     - 点击选项卡中的“反馈”选项；
#     - 输入反馈信息；
#     - 点击“提交”按钮。

# #### 注意事项

# - 用户名和密码是登录系统的凭证，请妥善保管。
# - 注册信息必须真实有效，以便系统为您提供准确的服务。
# - 缴费金额必须正确无误，以免造成误操作。
# - 个人信息修改后，请及时保存。
# - 查询条件请根据实际情况选择。
# - 反馈问题请尽量详细描述，以便系统及时处理。
# """
#     )
