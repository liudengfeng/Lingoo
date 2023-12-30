import json

# import google.generativeai as genai
import vertexai
from google.cloud import aiplatform
from google.oauth2.service_account import Credentials
from vertexai.preview.generative_models import HarmBlockThreshold, HarmCategory

# 屏蔽大部分
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_LOW_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_LOW_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_LOW_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_LOW_AND_ABOVE"},
]

# BLOCK_LOW_AND_ABOVE 会触发大部分的屏蔽
HARM_BLOCK_CONFIG = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
}

DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}


# def gemini_configure(secrets):
#     GOOGLE_API_KEY = secrets["Google"]["GEMINI_KEY"]
#     genai.configure(api_key=GOOGLE_API_KEY)


def get_tran_api_service_account_info(secrets):
    # 由于private_key含有大量的换行符号，所以单独存储
    service_account_info = json.loads(secrets["Google"]["TRANSLATE_API_CREDENTIALS"])
    service_account_info["private_key"] = secrets["Google"]["TRANSLATE_API_PRIVATE_KEY"]
    return service_account_info


def get_firestore_api_service_account_info(secrets):
    # 由于private_key含有大量的换行符号，所以单独存储
    service_account_info = json.loads(secrets["Google"]["FIRESTORE_API_CREDENTIALS"])
    service_account_info["private_key"] = secrets["Google"]["FIRESTORE_API_PRIVATE_KEY"]
    return service_account_info


def get_vertextai_service_account_info(secrets):
    # 由于private_key含有大量的换行符号，所以单独存储
    service_account_info = json.loads(secrets["Google"]["GLLM"])
    service_account_info["private_key"] = secrets["Google"]["GLLM_PRIVATE_KEY"]
    return service_account_info


def vertexai_configure(secrets):
    project = "gllm-409401"
    location = "asia-northeast1"
    # 完成认证及初始化
    service_account_info = get_vertextai_service_account_info(secrets)
    # 创建凭据
    credentials = Credentials.from_service_account_info(service_account_info)
    aiplatform.init(
        # your Google Cloud Project ID or number
        # environment default used is not set
        project=project,
        # the Vertex AI region you will use
        # defaults to us-central1
        location=location,
        # Google Cloud Storage bucket in same region as location
        # used to stage artifacts
        # staging_bucket="gs://my_staging_bucket",
        # custom google.auth.credentials.Credentials
        # environment default credentials used if not set
        credentials=credentials,
        # customer managed encryption key resource name
        # will be applied to all Vertex AI resources if set
        # encryption_spec_key_name=my_encryption_key_name,
        # the name of the experiment to use to track
        # logged metrics and parameters
        experiment="lingoo-experiment",
        # description of the experiment above
        experiment_description="云端使用vertex ai",
    )
    vertexai.init(project=project, location=location)
