import os
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient
from PIL import Image
from pymongo.errors import DuplicateKeyError

from mypylib.auth_utils import is_valid_email, is_valid_phone_number
from mypylib.authenticate import DbInterface
from mypylib.constants import FAKE_EMAIL_DOMAIN
from mypylib.db_model import User
from mypylib.constants import PROVINCES

current_cwd: Path = Path(__file__).parent.parent
wxskm_dir = current_cwd / "resource" / "wxskm"
feedback_dir = current_cwd / "resource" / "feedback"

# 创建Authenticator实例

st.set_page_config(
    page_title="用户管理",
    page_icon="👤",
    layout="wide",
)

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "dbi" not in st.session_state:
    st.session_state["dbi"] = DbInterface()

items = ["用户注册", "选择套餐", "更新信息", "重置密码", "统计报表", "问题反馈"]
tabs = st.tabs(items)


# region 创建注册页面

with tabs[items.index("用户注册")]:
    st.subheader("用户注册")

    with st.form(key="registration_form"):
        phone_number = st.text_input(
            "手机号码",
            key="phone_number",
            help="请输入有效手机号码",
            placeholder="必须",
        )
        email = st.text_input(
            "邮箱", key="email", help="请输入您常用的电子邮件地址", placeholder="可选。请输入您常用的电子邮件地址"
        )
        name = st.text_input(
            "个人姓名",
            key="name",
            help="成绩册上的姓名",
            placeholder="可选。如果您希望展示您的成就（例如：获得的奖项、完成的项目等），请在此处填写。",
        )
        username_reg = st.text_input(
            "用户名称", key="username_reg", help="登录显示名称", placeholder="必须。请输入您希望使用的用户名"
        )
        province = st.selectbox("省份", PROVINCES, index=0, key="province")
        password_reg = st.text_input(
            "密码",
            type="password",
            key="password_reg",
            help="密码长度至少为8位",
            placeholder="请输入您希望使用的密码，至少为8位",
        )
        password_reg_repeat = st.text_input(
            "密码",
            type="password",
            key="password_reg_repeat",
            # help="请再次输入密码",
            placeholder="为了确认，再次输入您刚才输入的密码",
        )
        status = st.empty()
        if st.form_submit_button(label="注册"):
            if phone_number is None or not is_valid_phone_number(phone_number):
                status.error("必须输入有效的手机号码")
                st.stop()
            if username_reg is None:
                status.error("必须输入有效的用户名")
                st.stop()
            if not email:
                # st.write(f"{email=}")
                status.warning("为了确保您能及时收到最新产品信息，请提供有效的邮箱地址。")
            elif not is_valid_email(email):
                status.error("请输入有效的邮箱地址")
                st.stop()
            if password_reg != password_reg_repeat:
                status.error("两次输入的密码不一致")
                st.stop()
            if len(password_reg) < 8:
                status.error("密码长度至少为8位")
                st.stop()

            user = User(
                # 由于邮箱作为索引，有必要保证其唯一性
                email=email if email else f"{phone_number}@{FAKE_EMAIL_DOMAIN}",
                name=name,
                username=username_reg,
                password=password_reg,
                province=province,
                phone_number=phone_number,
                registration_time=datetime.utcnow(),
            )  # type: ignore

            try:
                st.session_state.dbi.register_user(user)
            except DuplicateKeyError:
                st.markdown(
                    """您输入的手机号码或邮箱已被注册。如果您已经付费，请使用以下方式直接登录：
1. 在“登录”选项，输入您已注册的手机号码或邮箱。
2. 输入默认密码：12345678。
3. 点击“登录”。
登录成功后，您可以修改个人信息。"""
                )
                st.stop()
            st.success(f"""恭喜{username_reg}注册成功！请在三天内完成付款，以便您尽快使用我们的服务。""")

        with st.expander("免责声明", expanded=False):
            st.markdown(
                """
            **免责声明**

            在注册过程中，我们只会收集您提供的最基本的信息，包括您的姓名、用户名、密码和手机号码。我们承诺，我们会尽我们最大的努力来保护您的个人信息，不会在未经您同意的情况下将您的个人信息分享给任何第三方。

            请注意，您的密码将被安全地存储在我们的系统中，我们的员工无法查看您的密码。如果您忘记了密码，您将需要重置密码。

            在使用我们的服务时，请遵守所有适用的法律和法规。我们保留在任何时候修改或终止我们的服务的权利。

            如果您对我们的隐私政策或免责声明有任何问题，或者您想查看、更正或删除您的个人信息，请联系我们。
            """
            )

# endregion

# region 创建缴费页面

with tabs[items.index("选择套餐")]:
    st.subheader("选择套餐")

    # Define pricing tiers
    pricing_tiers = [
        {
            "title": "黄金版",
            "price": "6570",
            "unit": "每年",
            "description": [
                "按天计费节约40%",
                "学习分析报告",
                "用英语与AI🤖对话",
                "成才奖励最多30%",
            ],
            "img_name": "zx.jpeg",
        },
        {
            "title": "白金版",
            "price": "1890",
            "unit": "每季度",
            "description": [
                "按天计费节约30%",
                "学习分析报告",
                "用英语与AI🤖对话",
                "成才奖励最多20%",
            ],
            "img_name": "pf.jpeg",
        },
        {
            "title": "星钻版",
            "price": "720",
            "unit": "每月",
            "description": [
                "按天计费节约20%",
                "学习分析报告",
                "",
                "成才奖励最多10%",
            ],
            "img_name": "gf.jpeg",
        },
        {
            "title": "尝鲜版",
            "price": "210",
            "unit": "每周",
            "description": [
                "按每天30元计费",
                "每天不限时学习",
                "",
                "随机小额红包🧧",
            ],
            "img_name": "pa.jpeg",
        },
    ]

    cols = st.columns(len(pricing_tiers))

    # Create a column for each pricing tier
    for col, tier in zip(cols, pricing_tiers):
        # with col.container():
        # col.header(tier["title"])
        col.subheader(f"￥{tier['price']} / {tier['unit']}")
        for feature in tier["description"]:
            col.write(f"➕ {feature}")
        # col.button(tier["img_name"])
        image = Image.open(wxskm_dir / tier["img_name"])
        col.image(image, width=100)

# endregion

# region 创建更新信息页面

with tabs[items.index("更新信息")]:
    st.subheader("更新个人信息")
    if not st.session_state.dbi.is_service_active(st.session_state["user_id"]):
        st.error("您尚未登录，无法更新个人信息。")
        st.stop()

    user = st.session_state.dbi.find_user(st.session_state["user_id"])
    with st.form(key="update_form"):
        st.text_input(
            "手机号码",
            key="phone_number-3",
            help="请输入有效手机号码",
            value=user["phone_number"],
            disabled=True,
        )
        email = st.text_input(
            "邮箱", key="email-3", help="请输入有效邮箱地址", value=user["email"]
        )
        name = st.text_input("个人姓名", key="name-3", help="成绩册上的姓名", value=user["name"])
        username_reg = st.text_input(
            "用户名称", key="username_reg-3", help="登录显示名称", value=user["username"]
        )
        status = st.empty()
        if st.form_submit_button(label="确认"):
            try:
                st.session_state.dbi.update_user(
                    st.session_state["user_id"],
                    {
                        "email": email,
                        "name": name,
                        "username": username_reg,
                    },
                )
                st.success("更新成功")
            except DuplicateKeyError:
                if email and not is_valid_email(email):
                    status.error("请输入有效的邮箱地址")
                    st.stop()
            except Exception as e:
                st.error(e)
                raise e
    #         if password_reg != password_reg_repeat:
    #             status.error("两次输入的密码不一致")
    #             st.stop()
    #         if len(password_reg) < 8:
    #             status.error("密码长度至少为8位")
    #             st.stop()
    #         user = User(
    #             email=email,
    #             name=name,
    #             username=username_reg,
    #             password=password_reg,
    #             phone_number=phone_number,
    #         )  # type: ignore
    #         dbi.register_user(user)
    #         st.success("Registration successful")

# endregion

# region 创建重置密码页面

with tabs[items.index("重置密码")]:
    st.subheader("重置密码")
    if not st.session_state.dbi.is_service_active(st.session_state["user_id"]):
        st.error("您尚未付费，无法使用此功能。")
        st.stop()
    user = User(**st.session_state.dbi.find_user(st.session_state["user_id"]))
    with st.form(key="secret_form", clear_on_submit=True):
        password_reg = st.text_input(
            "密码", type="password", key="password_reg-4", help="密码长度至少为8位"
        )
        password_reg_repeat = st.text_input(
            "密码", type="password", key="password_reg_repeat-4", help="请再次输入密码"
        )
        status = st.empty()
        if st.form_submit_button(label="确认"):
            if password_reg != password_reg_repeat:
                status.error("两次输入的密码不一致")
                st.stop()
            user.password = password_reg
            user.hash_password()
            st.session_state.dbi.update_user(
                st.session_state["user_id"],
                {
                    "password": user.password,
                },
            )
            st.success("成功重置密码")
            st.session_state.dbi.logout(phone_number=user.phone_number)

# endregion

# region 创建统计页面

with tabs[items.index("统计报表")]:
    st.subheader("统计报表")
    if not st.session_state.dbi.is_service_active(st.session_state["user_id"]):
        st.error("您尚未登录，无法查阅统计报表。")
        st.stop()
# endregion

# region 创建反馈页面


with tabs[items.index("问题反馈")]:
    with st.form(key="feedback_form"):
        title = st.text_input("标题", key="title", help="请输入标题")
        content = st.text_area("问题描述", key="content", help="请输入内容")
        uploaded_file = st.file_uploader(
            "📁 上传截屏视频", type=["webm"],help="请按'如何录制截屏视频'指引，录制视频反馈给管理员。")
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
            text_data = f"用户：{st.session_state['user_id']}\n标题: {title}\n内容: {content}"

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
        image_1 = Image.open(feedback_dir / "step-1.png")
        st.image(image_1, width=200)

        st.markdown(
            """2. 单击"Record a screencast"。
    3. 如果要通过麦克风录制音频，请选中"Also record audio"。
    """
        )
        image_2 = Image.open(feedback_dir / "step-2.png")
        st.image(image_2, width=400)

        st.markdown(
            """4. 单击"Start recording!"。(操作系统可能会提示您允许浏览器录制屏幕或使用麦克风。)
    5. 从列出的选项中选择要录制的选项卡、窗口或监视器。界面会因您的浏览器而异。
    """
        )
        image_3 = Image.open(feedback_dir / "step-3.png")
        st.image(image_3, width=400)

        st.markdown(
            """6. 单击"共享"。
    """
        )
        image_4 = Image.open(feedback_dir / "step-4.png")
        st.image(image_4, width=400)

        st.markdown(
            """
7. 录制时，您将在应用程序的选项卡和应用程序菜单图标上看到一个红色圆圈。如果您想取消录制，请单击应用程序底部的“停止共享”。
    """
        )
        image_5 = Image.open(feedback_dir / "step-5.png")
        st.image(image_5, width=400)

        st.markdown(
            """
8. 完成录制后，按键盘上的“Esc”或单击应用程序菜单中的“停止录制”。
    """
        )
        image_6 = Image.open(feedback_dir / "step-6.png")
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
