import streamlit as st
import vertexai
from google.cloud import firestore, translate
from google.oauth2.service_account import Credentials
from vertexai.preview.generative_models import GenerativeModel

from .db_interface import DbInterface
from .google_cloud_configuration import (
    LOCATION,
    PROJECT_ID,
    get_firestore_api_service_account_info,
    get_tran_api_service_account_info,
    vertexai_configure,
)


def common_page_config():
    if "dbi" not in st.session_state:
        st.session_state["dbi"] = DbInterface(get_firestore_client())


def configure_google_apis():
    # 配置 AI 服务
    if st.secrets["env"] in ["streamlit", "azure"]:
        if "inited_google_ai" not in st.session_state:
            vertexai_configure(st.secrets)
            # vertexai.init(project=PROJECT_ID, location=LOCATION)
            st.session_state["inited_google_ai"] = True

        # 配置 token 计数器
        if "current_token_count" not in st.session_state:
            st.session_state["current_token_count"] = 0

        # 应该存放在数据库
        if "total_token_count" not in st.session_state:
            st.session_state["total_token_count"] = 0
    else:
        st.warning("非云端环境，无法使用 Google AI", icon="⚠️")
        # st.stop()


def check_and_force_logout(status):
    """
    检查并强制退出用户重复登录。

    Args:
        st (object): Streamlit 模块。
        status (object): Streamlit 状态元素，用于显示错误信息。

    Returns:
        None
    """
    if "session_id" in st.session_state.dbi.cache:
        dbi = st.session_state.dbi
        # 存在会话id，说明用户已经登录
        phone_number = dbi.cache["phone_number"]
        # 获取除最后一个登录事件外的所有未退出的登录事件
        active_sessions = dbi.get_active_sessions()
        for session in active_sessions:
            if session["session_id"] == dbi.cache.get("session_id", ""):
                # 如果 st.session_state 中的会话ID在需要强制退出的列表中，处理强制退出
                dbi.force_logout_session(phone_number, session["session_id"])
                st.session_state.clear()
                status.error("您的账号在其他设备上登录，您已被强制退出。")
                st.stop()


def authenticate_and_configure_services():
    common_page_config()
    if "google_translate_client" not in st.session_state:
        st.session_state["google_translate_client"] = get_translation_client()
    configure_google_apis()


@st.cache_resource
def get_translation_client():
    service_account_info = get_tran_api_service_account_info(st.secrets)
    # 创建凭据
    credentials = Credentials.from_service_account_info(service_account_info)
    # 使用凭据初始化客户端
    return translate.TranslationServiceClient(credentials=credentials)


@st.cache_resource
def get_firestore_client():
    service_account_info = get_firestore_api_service_account_info(st.secrets)
    # 创建凭据
    credentials = Credentials.from_service_account_info(service_account_info)
    # 使用凭据初始化客户端
    return firestore.Client(credentials=credentials, project=PROJECT_ID)


@st.cache_resource
def load_vertex_model(model_name):
    return GenerativeModel(model_name)


def check_access(is_admin_page):
    if "dbi" not in st.session_state:
        st.session_state["dbi"] = DbInterface(get_firestore_client())

    if not st.session_state.dbi.is_logged_in():
        st.error("您尚未登录。请前往首页左侧栏进行登录。")
        st.stop()

    if is_admin_page and st.session_state.dbi.cache.get("user_role") != "管理员":
        st.error("您没有权限访问此页面。此页面仅供系统管理员使用。")
        st.stop()


def google_translate(text: str, target_language_code: str = "zh-CN"):
    """Translating Text."""
    if text is None or text == "":
        return text  # type: ignore

    # Location must be 'us-central1' or 'global'.
    parent = f"projects/{PROJECT_ID}/locations/global"

    client = st.session_state.google_translate_client
    # Detail on supported types can be found here:
    # https://cloud.google.com/translate/docs/supported-formats
    response = client.translate_text(
        request={
            "parent": parent,
            "contents": [text],
            "mime_type": "text/plain",  # mime types: text/plain, text/html
            "source_language_code": "en-US",
            "target_language_code": target_language_code,
        }
    )

    res = []
    # Display the translation for each input text provided
    for translation in response.translations:
        res.append(translation.translated_text.encode("utf8").decode("utf8"))
    # google translate api 返回一个结果
    return res[0]
