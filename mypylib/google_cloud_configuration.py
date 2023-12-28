import json

import google.generativeai as genai
from google.cloud import aiplatform, translate
from google.oauth2.service_account import Credentials
from vertexai.preview.generative_models import HarmBlockThreshold, HarmCategory

# 屏蔽大部分
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_LOW_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_LOW_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_LOW_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_LOW_AND_ABOVE"},
]

NORMAL_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
}


def gemini_configure(secrets):
    GOOGLE_API_KEY = secrets["Google"]["GEMINI_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)


def get_service_account_info(secrets):
    # 由于private_key含有大量的换行符号，所以单独存储
    service_account_info = json.loads(secrets["Google"]["TRANSLATE_API_CREDENTIALS"])
    service_account_info["private_key"] = secrets["Google"]["TRANSLATE_API_PRIVATE_KEY"]
    return service_account_info


def get_translation_client(secrets):
    service_account_info = get_service_account_info(secrets)
    # 创建凭据
    credentials = Credentials.from_service_account_info(service_account_info)
    # 使用凭据初始化客户端
    return translate.TranslationServiceClient(credentials=credentials)
