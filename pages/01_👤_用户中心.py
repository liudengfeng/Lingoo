import locale
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytz
import streamlit as st
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient
from cryptography.fernet import Fernet
from PIL import Image
from pymongo.errors import DuplicateKeyError

from mypylib.auth_utils import is_valid_email, is_valid_phone_number
from mypylib.constants import FAKE_EMAIL_DOMAIN, PROVINCES
from mypylib.db_interface import DbInterface
from mypylib.db_model import User
from mypylib.streamlit_helper import check_and_force_logout

CURRENT_CWD: Path = Path(__file__).parent.parent
WXSKM_DIR = CURRENT_CWD / "resource" / "wxskm"
FEEDBACK_DIR = CURRENT_CWD / "resource" / "feedback"

# 创建 Fernet 实例【必须将key转换为bytes类型】
fernet = Fernet(st.secrets["FERNET_KEY"].encode())

st.set_page_config(
    page_title="用户管理",
    page_icon="👤",
    layout="wide",
)

if "user_info" not in st.session_state:
    st.session_state["user_info"] = {}

if "dbi" not in st.session_state:
    st.session_state["dbi"] = DbInterface()


# region 侧边栏

sidebar_status = st.sidebar.empty()
# 在页面加载时检查是否有需要强制退出的登录会话
check_and_force_logout(st, sidebar_status)

# endregion

emojis = ["👤", "🍱", "🔄", "🔑", "📊", "📝"]
item_names = ["用户注册", "选择套餐", "更新信息", "重置密码", "统计报表", "问题反馈"]
items = [f"{e} {n}" for e, n in zip(emojis, item_names)]
tabs = st.tabs(items)


# region 创建注册页面

with tabs[items.index("👤 用户注册")]:
    st.subheader("👤 用户注册")

    with st.form(key="registration_form"):
        col1, col2 = st.columns(2)
        phone_number = col1.text_input(
            "手机号码",
            key="phone_number",
            help="请输入有效手机号码",
            placeholder="必须",
        )
        email = col2.text_input(
            "邮箱", key="email", help="请输入您常用的电子邮件地址", placeholder="可选。请输入您常用的电子邮件地址"
        )
        real_name = col1.text_input(
            "真实姓名",
            key="real_name",
            help="成绩册上的姓名",
            placeholder="可选。如果您希望展示您的成就（例如：获得的奖项、完成的项目等），请在此处填写。",
        )
        display_name = col2.text_input(
            "显示名称", key="display_name", help="登录显示名称", placeholder="必须。请输入您希望使用的用户名"
        )
        current_level = col1.selectbox(
            "当前英语水平",
            ["A1", "A2", "B1", "B2", "C1", "C2"],
            index=0,
            key="current_level",
            help="如果您不了解如何分级，请参阅屏幕下方关于CEFR分级的说明",
        )
        target_level = col2.selectbox(
            "期望达到的英语水平",
            ["A1", "A2", "B1", "B2", "C1", "C2"],
            index=5,
            key="target_level",
            help="如果您不了解如何分级，请参阅屏幕下方关于CEFR分级的说明",
        )
        country = col1.selectbox(
            "所在国家",
            ["中国"],
            index=0,
            key="country",
        )
        province = col2.selectbox("所在省份", PROVINCES, index=0, key="province")
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
        tz = col1.selectbox(
            "所在时区",
            pytz.common_timezones,
            index=pytz.common_timezones.index("Asia/Shanghai"),
            key="timezone",
            help="请根据您当前所在的时区选择。如果您在中国，请使用默认值。",
        )
        agree = st.checkbox(
            "我同意《服务条款》",
            key="agree",
            value=False,
            help="请仔细阅读《服务条款》，并勾选此项。",
        )
        status = st.empty()
        if st.form_submit_button(label="注册"):
            if not agree:
                status.error("请仔细阅读《服务条款》，并勾选同意。")
                st.stop()
            if phone_number is None or not is_valid_phone_number(phone_number):
                status.error("必须输入有效的手机号码")
                st.stop()
            if display_name is None:
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

            # 由于邮箱作为索引，有必要保证其唯一性
            email = email if email else f"{phone_number}@{FAKE_EMAIL_DOMAIN}"
            user = User(
                # 加密字段
                f_email=fernet.encrypt(email.encode()),
                f_real_name=fernet.encrypt(real_name.encode()),
                f_country=fernet.encrypt(country.encode()),
                f_province=fernet.encrypt(province.encode()),
                f_timezone=fernet.encrypt(tz.encode()),
                # 普通字段
                phone_number=phone_number,
                current_level=current_level,
                target_level=target_level,
                display_name=display_name,
                password=password_reg,
                registration_time=datetime.now(timezone.utc),
            )  # type: ignore

            user.hash_password()
            try:
                st.session_state.dbi.register_user(user)
            except DuplicateKeyError as e:
                # 如果抛出 DuplicateKeyError 异常，从异常的消息中解析出字段的名称
                field_name = str(e).split("index: ")[1].split(" dup key")[0]
                msg = "邮箱" if field_name.startswith("f_email") else "电话号码"
                status.markdown(
                    f"""
                **您输入的{msg}已被注册。**
                如果您已完成付款，系统会自动为您注册，请使用以下方式直接登录：
                1. 在左侧菜单“用户中心”的“登录”选项，输入您已注册的手机号码。
                2. 输入默认密码：12345678。
                3. 点击“确定”按钮。
                登录成功后，您可以在“用户中心”修改个人信息。"""
                )
                st.stop()
            # 截至付款期限
            deadline = datetime.now(timezone.utc) + timedelta(days=3)
            # 创建一个时区对象
            tz = pytz.timezone(tz)  # 请将 'Asia/Shanghai' 替换为你的时区
            # 将 UTC 时间转换为特定的时区
            deadline = deadline.astimezone(tz)
            deadline_str = deadline.strftime("%Y-%m-%d %H:%M:%S")
            st.success(
                f"""恭喜{display_name}注册成功！为确保您能尽快体验我们的服务，请于{deadline_str}前完成付款。"""
            )

        with st.expander("**服务条款**", expanded=False):
            st.markdown(
                """
            **服务条款**

**1. 服务概述**

**英语应用能力提升应用服务条款**

**1. 服务概述**

`LinGoo` [英语速学] app（以下简称“本应用”）是由 DF studio 提供的一种使用大型生成式语言模型作为教学辅助工具，帮助用户提升英语应用能力的服务。本应用基于互联网，为用户提供丰富的学习资源和互动功能，帮助用户在英语应用能力各方面取得提升。本应用的目标用户是具有一定英语基础，希望提升英语应用能力的用户。

**2. 服务使用条件**

使用本应用，用户需要满足以下条件：

* 年满 12 周岁，且具有自主行为能力。
* 具有正常的阅读、听力、口语能力。
* 应具有良好的网络环境，能够正常使用本应用的功能。
* 熟练掌握电脑上网浏览基本操作。
* 配备麦克风、耳机硬件，可正常收听音频、录音。
* 同意遵守本服务条款。

**3. 服务费用**

* 本应用不提供试用服务。
* 学习类功能实行期限订阅，用户可根据自身需求选择订阅周期。订阅周期为 1 周、 1 个月、3 个月、6 个月、1 年。
* 聊天机器人、评估类功能实现限时按次付费，用户可根据自身需要选择付费次数。
* 订阅期内，用户可无限次使用学习类功能，但聊天机器人、评估类功能的使用次数根据用户购买的次数限制。

具体价格表可在本应用的网站查询。

**4. 服务变更**

DF studio 有权对本应用的服务内容、服务费用、服务条款等进行变更。用户在注册本应用时，需阅读并同意《服务条款》。用户在变更后继续使用本应用，视为同意接受变更后的服务内容、服务费用。
DF studio 有权在合理范围内对本服务条款进行变更，变更后的服务条款将在本应用的官方网站或其他适当渠道发布，用户在变更后继续使用本应用，视为同意接受变更后的服务条款。

**5. 免责声明**

DF studio 对本应用的使用不提供任何明示或暗示的担保，包括但不限于对本应用的正确性、完整性、及时性、安全性、可靠性等。

DF studio 对用户使用本应用过程中产生的任何损失，包括但不限于直接损失、间接损失、附带损失、衍生损失等，不承担任何责任。

**6. 争议解决**

本服务条款的解释和执行，适用中华人民共和国法律。

因本服务条款引起的任何争议，由 DF studio 与用户友好协商解决。协商不成的，任何一方均可向仲裁机构提起仲裁。仲裁裁决是终局的，对双方均具有约束力。

**7. 其他**

* **隐私政策**

第 1 条 用户个人信息保护用户有权查阅、修改或删除其个人信息。用户可以通过本应用的“用户中心”功能进行操作。

**第 2 条 用户个人信息保护**

DF Studio 尊重用户的隐私权，会采取一切合理的措施保护用户的隐私。

**(一) 用户个人信息的收集**

注册本应用时，DF Studio 会收集用户的以下个人信息：

* 用户名
* 个人密码
* 真实姓名
* 手机号码
* 个人邮箱
* 当前英语水平
* 期望达到的英语水平
* 所在国家
* 所在省份
* 所在时区

**(二) 用户个人信息的使用**

DF Studio 会将用户个人信息用于以下目的：

* 提供本应用的服务：DF Studio 会使用用户个人信息来提供本应用的基础功能，例如用户登录、用户信息展示等。
* 改善本应用的服务：DF Studio 会使用用户个人信息来分析用户行为，以改进本应用的功能和性能。
* 向用户发送服务升级信息：DF Studio 会使用用户个人信息来向用户发送服务升级信息，例如新功能介绍、安全公告等

**(三) 用户个人信息的安全**

DF Studio 会采取以下措施保护用户个人信息的安全：

* 除用户手机号码外，所有个人隐私信息均采用安全加密算法存储在数据库中，仅对应用程序服务器可访问。
* 应用程序服务器使用访问控制列表（ACL）来限制对个人隐私信息的访问，只有系统管理员才有权查看。
* 用户密码采用加密技术，有效保护用户密码的安全，即使 DF Studio 员工也不可能获得用户密码。

| 项目 | 加密存储 | 明文存储 | 权限 | 说明 |
|---|:-:|:-:|---|---|
| 用户名 | 否 | 是 | 不限 | 用于在app显示用户自定义的名称 |
| 个人密码 | 是 | 否 | 仅用户可见 | 用于登录应用程序 |
| 真实姓名 | 是 | 否 | 仅用户、系统管理员可见 | 个人隐私信息 |
| 手机号码 | 否 | 是 | 仅用户、系统管理员可见 |app交互|
| 真实姓名 | 是 | 否 | 仅用户、系统管理员可见 | 个人隐私信息 |
| 个人邮箱 | 是 | 否 | 仅用户、系统管理员可见 | 个人隐私信息 |
| 所在国家 | 是 | 否 | 仅用户、系统管理员可见 | 个人隐私信息 |
| 所在省份 | 是 | 否 | 仅用户、系统管理员可见 | 个人隐私信息 |
| 所在时区 | 是 | 否 | 仅用户、系统管理员可见 | 个人隐私信息 |

* **数据使用**

DF studio 可能会使用用户的数据来提供本应用的服务，包括但不限于：

> * 为用户提供个性化的学习内容和推荐。
> * 分析用户的使用行为，以改进本应用的服务。

用户有权要求DF studio 删除其数据。

* **使用聊天机器人**
> * 聊天机器人使用的是一种人工智能技术，具有一定的学习和生成能力，用户应对其功能和局限性有正确的认识，避免使用聊天机器人进行任何违法或有害的行为，并对聊天机器人生成的信息进行合理的判断和评估。
> * 用户不得使用本应用生成任何虚假或误导性、侵犯他人权利或利益、具有歧视性或仇恨性、具有危险性或破坏性的信息。
> * 用户在使用本应用的聊天机器人时，不得发表以下内容：

 >>> - 关于政治人物的负面言论，包括但不限于诽谤、污蔑、造谣等。
 >>> - 传播宗教极端主义思想，包括但不限于宣扬暴力、恐怖、分裂等。
 >>> - 传播色情、暴力等违法信息，包括但不限于淫秽、色情、暴力、恐怖等。
 >>> - 宣传非法集资、传销等违法活动，包括但不限于非法集资、传销、诈骗等。

> * 用户不得使用聊天机器人进行以下活动：

 >>> - 发布、传播任何违反国家法律法规、政策的内容。
 >>> - 使用本应用生成任何具有歧视性或仇恨性的信息。
 >>> - 发布、传播上述内容。
 >>> - 与他人进行上述内容的讨论。

> **违反上述规定的，用户将承担相应的法律责任。**
"""
            )

        with st.expander("**CEFR（欧洲共同语言参考标准）语言能力分级标准**", expanded=False):
            st.markdown(
                """\
- A1：入门级

    - 能够理解并运用与自己最切身相关且经常使用的表达方式和非常简单的语句，例如：个人的姓名、家庭成员、基本日常活动、购物等。
    - 能够用简单的句子与他人进行简单的交流，例如：介绍自己、询问和回答有关个人的信息等。
  
- A2：初级

    - 能够理解并运用日常生活中经常使用的表达方式和简单的语句，例如：基本个人和家庭信息、购物、地理位置、就业等。
    - 能够用简单的句子表达个人的需要、想法和感受，例如：介绍自己的兴趣爱好、谈论自己的计划等。

- B1：中级

    - 能够理解日常生活中常见的口头和书面信息，例如：工作、学习、休闲等方面的信息。
    - 能够用简单的句子和语段表达日常生活和工作中常见的主题，例如：描述个人经历、谈论自己的计划和愿望等。

- B2：中高级

    - 能够理解日常生活中和工作中广泛的口头和书面信息，例如：新闻报道、教育课程、专业文献等。
    - 能够用清晰的句子和语段表达复杂的主题，例如：讨论观点、分析问题等。

- C1：高级

    - 能够理解复杂的口头和书面信息，例如：长篇文章、专业文献等。
    - 能够用流利、准确的语言表达复杂的主题，例如：分析、批评、总结等。

- C2：熟练级

    - 能够理解任何口头和书面信息，无论其复杂程度如何。
    - 能够用流利、准确、自然的语言表达任何主题，例如：阐述观点、辩论、创作等。
"""
            )
# endregion

# region 创建缴费页面

with tabs[items.index("🍱 选择套餐")]:
    st.subheader("🍱 选择套餐")

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
        image = Image.open(WXSKM_DIR / tier["img_name"])
        col.image(image, width=100)

# endregion

# region 创建更新信息页面

with tabs[items.index("🔄 更新信息")]:
    st.subheader("🔄 更新个人信息")
    if not st.session_state.dbi.is_service_active(st.session_state.user_info):
        st.error("您的账号未登录，或者尚未缴费、激活，无法更新个人信息。")
        st.stop()
    CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"]
    COUNTRIES = ["中国"]
    user_doc = st.session_state.dbi.find_user(st.session_state.user_info["user_id"])
    user = User.from_doc(user_doc)
    user.set_secret_key(st.secrets["FERNET_KEY"])

    with st.form(key="update_form"):
        col1, col2 = st.columns(2)
        col1.text_input(
            "手机号码",
            key="phone_number-3",
            help="请输入有效手机号码",
            value=user.phone_number,
            disabled=True,
        )
        email = col2.text_input("邮箱", key="email-3", help="请输入有效邮箱地址", value=user.email)
        real_name = col1.text_input(
            "真实姓名",
            key="real_name-3",
            help="成绩册上的姓名",
            value=user.real_name,
        )
        display_name = col2.text_input(
            "显示名称", key="display_name-3", help="登录显示名称", value=user.display_name
        )
        current_level = col1.selectbox(
            "当前英语水平",
            CEFR,
            index=CEFR.index(user.current_level),
            key="current_level-3",
            help="如果您不了解如何分级，请参阅屏幕下方关于CEFR分级的说明",
        )
        target_level = col2.selectbox(
            "期望达到的英语水平",
            CEFR,
            index=CEFR.index(user.target_level),
            key="target_level-3",
            help="如果您不了解如何分级，请参阅屏幕下方关于CEFR分级的说明",
        )
        country = col1.selectbox(
            "所在国家",
            COUNTRIES,
            index=COUNTRIES.index(user.country),
            key="country-3",
        )
        province = col2.selectbox("所在省份", PROVINCES, index=0, key="province-3")
        tz = col1.selectbox(
            "所在时区",
            pytz.common_timezones,
            index=pytz.common_timezones.index(user.timezone),
            key="timezone-3",
            help="请根据您当前所在的时区选择。如果您在中国，请使用默认值。",
        )
        status = st.empty()
        if st.form_submit_button(label="确认"):
            try:
                st.session_state.dbi.update_user(
                    st.session_state.user_info["user_id"],
                    {
                        "f_email": fernet.encrypt(email.encode()),
                        "f_real_name": fernet.encrypt(real_name.encode()),
                        "f_country": fernet.encrypt(country.encode()),
                        "f_province": fernet.encrypt(province.encode()),
                        "f_timezone": fernet.encrypt(tz.encode()),
                        "display_name": display_name,
                        "current_level": current_level,
                        "target_level": target_level,
                    },
                )
                status.success("更新成功")
                time.sleep(3)
                st.rerun()
            except DuplicateKeyError:
                if email and not is_valid_email(email):
                    status.error("请输入有效的邮箱地址")
                    st.stop()
            except Exception as e:
                st.error(e)
                raise e

# endregion

# region 创建重置密码页面

with tabs[items.index("🔑 重置密码")]:
    st.subheader("🔑 重置密码")
    if len(
        st.session_state.user_info
    ) == 0 or not st.session_state.dbi.is_service_active(st.session_state.user_info):
        st.error("您的账号尚未缴费、激活，无法重置密码。")
        st.stop()

    user_doc = st.session_state.dbi.find_user(st.session_state.user_info["user_id"])
    user = User.from_doc(user_doc)
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
            # TODO：查看返回结果
            st.write(
                st.session_state.dbi.update_user(
                    st.session_state.user_info["user_id"],
                    {
                        "password": user.password,
                    },
                )
            )
            st.success("成功重置密码")
            st.session_state.dbi.logout(phone_number=user.phone_number)

# endregion

# region 创建统计页面

with tabs[items.index("📊 统计报表")]:
    st.subheader("📊 统计报表")

    if not st.session_state.dbi.is_service_active(st.session_state.user_info):
        st.error("您尚未登录，无法查阅统计报表。")
        st.stop()

# endregion

# region 创建反馈页面

uploaded_emoji = "📁"

with tabs[items.index("📝 问题反馈")]:
    if not st.session_state.dbi.is_service_active(st.session_state.user_info):
        st.error("您尚未登录，无法反馈问题。")
        st.stop()

    with st.form(key="feedback_form"):
        title = st.text_input("标题", key="title", help="请输入标题")
        content = st.text_area("问题描述", key="content", help="请输入内容")
        uploaded_file = st.file_uploader(
            f"{uploaded_emoji} 上传截屏视频",
            type=["webm"],
            help="请按<<如何录制截屏视频>>指引，录制视频反馈给管理员。",
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
            text_data = f"用户：{st.session_state.user_info['user_id']}\n标题: {title}\n内容: {content}"

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
