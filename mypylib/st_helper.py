import logging
from datetime import datetime
import time
from azure.storage.blob import BlobServiceClient
import pytz
import streamlit as st
import vertexai
from google.cloud import firestore, translate
from google.oauth2.service_account import Credentials
from vertexai.preview.generative_models import GenerativeModel

from .db_interface import DbInterface
from .google_cloud_configuration import (
    LOCATION,
    PROJECT_ID,
    get_google_service_account_info,
    google_configure,
)


def setup_logger(logger, level="INFO"):
    # 设置日志的时间戳为 Asia/Shanghai 时区
    formatter = logging.Formatter("%(asctime)s - %(message)s")
    formatter.converter = lambda *args: datetime.now(
        tz=pytz.timezone("Asia/Shanghai")
    ).timetuple()
    for handler in logger.handlers:
        handler.setFormatter(formatter)
        handler.setLevel(logging.getLevelName(level))


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


@st.cache_resource
def get_translation_client():
    service_account_info = get_google_service_account_info(st.secrets)
    # 创建凭据
    credentials = Credentials.from_service_account_info(service_account_info)
    # 使用凭据初始化客户端
    return translate.TranslationServiceClient(credentials=credentials)


@st.cache_resource
def get_firestore_client():
    service_account_info = get_google_service_account_info(st.secrets)
    # 创建凭据
    credentials = Credentials.from_service_account_info(service_account_info)
    # 使用凭据初始化客户端
    return firestore.Client(credentials=credentials, project=PROJECT_ID)


@st.cache_resource
def load_vertex_model(model_name):
    return GenerativeModel(model_name)


@st.cache_resource
def get_blob_service_client():
    # container_name = "word-images"
    connect_str = st.secrets["Microsoft"]["AZURE_STORAGE_CONNECTION_STRING"]
    # 创建 BlobServiceClient 对象
    return BlobServiceClient.from_connection_string(connect_str)


@st.cache_resource
def get_blob_container_client(container_name):
    # 创建 BlobServiceClient 对象
    blob_service_client = get_blob_service_client()
    # 获取 ContainerClient 对象
    return blob_service_client.get_container_client(container_name)


def check_access(is_admin_page):
    if "dbi" not in st.session_state:
        st.session_state["dbi"] = DbInterface(get_firestore_client())

    if not st.session_state.dbi.is_logged_in():
        st.error("您尚未登录。请点击屏幕左侧的 `Home` 菜单进行登录。")
        st.stop()

    if is_admin_page and st.session_state.dbi.cache.get("user_role") != "管理员":
        st.error("您没有权限访问此页面。此页面仅供系统管理员使用。")
        st.stop()


def configure_google_apis():
    # 配置 AI 服务
    if st.secrets["env"] in ["streamlit", "azure"]:
        if "inited_google_ai" not in st.session_state:
            google_configure(st.secrets)
            # vertexai.init(project=PROJECT_ID, location=LOCATION)
            st.session_state["inited_google_ai"] = True

        if "google_translate_client" not in st.session_state:
            st.session_state["google_translate_client"] = get_translation_client()

        # 配置 token 计数器
        if "current_token_count" not in st.session_state:
            st.session_state["current_token_count"] = 0

        if "total_token_count" not in st.session_state:
            st.session_state[
                "total_token_count"
            ] = st.session_state.dbi.get_token_count()
    else:
        st.warning("非云端环境，无法使用 Google AI", icon="⚠️")


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


def format_token_count(count):
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)


def update_and_display_progress(
    current_value: int, total_value: int, progress_bar, message=""
):
    """
    更新并显示进度条。

    Args:
        current_value (int): 当前值。
        total_value (int): 总值。
        progress_bar: Streamlit progress bar object.

    Returns:
        None
    """
    # 计算进度
    progress = current_value / total_value

    # 显示进度百分比
    text = f"{progress:.2%} {message}"

    # 更新进度条的值
    progress_bar.progress(progress, text)


def view_stream_response(responses, placeholder):
    """
    Concatenates the text from the given responses and displays it in a placeholder.

    Args:
        responses (list): A list of response chunks.
        placeholder: The placeholder where the concatenated text will be displayed.
    """
    full_response = ""
    for chunk in responses:
        try:
            full_response += chunk.text
        except (IndexError, ValueError) as e:
            st.write(chunk)
            st.error(e)
            # pass
        time.sleep(0.05)
        # Add a blinking cursor to simulate typing
        placeholder.markdown(full_response + "▌")
    placeholder.markdown(full_response)
