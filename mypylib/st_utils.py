import streamlit as st
import vertexai
from google.cloud import translate
from google.oauth2.service_account import Credentials
from vertexai.preview.generative_models import GenerativeModel

from .db_interface import DbInterface
from .google_cloud_configuration import gemini_configure, get_service_account_info

PROJECT_ID = "gllm-409401"
LOCATION = "asia-northeast1"


def common_page_config():
    if "user_info" not in st.session_state:
        st.session_state["user_info"] = {}
    if "dbi" not in st.session_state:
        st.session_state["dbi"] = DbInterface()


def configure_google_apis():
    # 配置 AI 服务
    if st.secrets["env"] in ["streamlit", "azure"]:
        if "inited_google_ai" not in st.session_state:
            # gemini_configure(st.secrets)
            vertexai.init(project=PROJECT_ID, location=LOCATION)
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
    if "user_info" in st.session_state and "session_id" in st.session_state.user_info:
        # 获取除最后一个登录事件外的所有未退出的登录事件
        active_sessions = st.session_state.dbi.get_active_sessions(
            st.session_state.user_info["user_id"]
        )
        for session in active_sessions:
            if session.session_id == st.session_state.user_info["session_id"]:
                # 如果 st.session_state 中的会话ID在需要强制退出的列表中，处理强制退出
                st.session_state.dbi.force_logout_session(
                    st.session_state.user_info["user_id"], session.session_id
                )
                st.session_state.clear()
                status.error("您的账号在其他设备上登录，您已被强制退出。")
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


def authenticate_and_configure_services():
    common_page_config()
    if not st.session_state.dbi.is_service_active(st.session_state["user_info"]):
        st.error("非付费用户，无法使用此功能。")
        st.stop()
    if "google_translate_client" not in st.session_state:
        st.session_state["google_translate_client"] = get_translation_client()
    configure_google_apis()


@st.cache_resource
def get_translation_client():
    service_account_info = get_service_account_info(st.secrets)
    # 创建凭据
    credentials = Credentials.from_service_account_info(service_account_info)
    # 使用凭据初始化客户端
    return translate.TranslationServiceClient(credentials=credentials)


@st.cache_resource
def load_model(model_name):
    return GenerativeModel(model_name)
