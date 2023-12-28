import json
from google.oauth2.service_account import Credentials
from google.cloud import aiplatform, translate


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
