import json

import vertexai
from google.cloud import aiplatform, translate
from google.oauth2.service_account import Credentials

project = "lingo-406201"
location = "asia-northeast1"


def get_service_account_info(secrets):
    # 由于private_key含有大量的换行符号，所以单独存储
    service_account_info = json.loads(
        secrets["Google"]["GOOGLE_APPLICATION_CREDENTIALS"]
    )
    service_account_info["private_key"] = secrets["Google"]["private_key"]
    return service_account_info


def get_translation_client(secrets):
    service_account_info = get_service_account_info(secrets)
    # 创建凭据
    credentials = Credentials.from_service_account_info(service_account_info)
    # 使用凭据初始化客户端
    return translate.TranslationServiceClient(credentials=credentials)


def translate_text(text: str, client):
    """Translating Text."""
    if text is None or text == "":
        return text  # type: ignore

    parent = f"projects/{project}/locations/{location}"

    # Detail on supported types can be found here:
    # https://cloud.google.com/translate/docs/supported-formats
    response = client.translate_text(
        request={
            "parent": parent,
            "contents": [text],
            "mime_type": "text/plain",  # mime types: text/plain, text/html
            "source_language_code": "en-US",
            "target_language_code": "zh",
        }
    )

    res = []
    # Display the translation for each input text provided
    for translation in response.translations:
        res.append(translation.translated_text.encode("utf8").decode("utf8"))
    # google translate api 返回一个结果
    return res[0]


def init_vertex(secrets):
    # 完成认证及初始化
    service_account_info = get_service_account_info(secrets)
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
        experiment="lingo-experiment",
        # description of the experiment above
        experiment_description="云端使用vertex ai",
    )
    vertexai.init(project=project, location=location)
