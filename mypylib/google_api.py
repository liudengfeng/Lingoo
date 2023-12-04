import json

import vertexai
from google.cloud import aiplatform, translate
from google.oauth2.service_account import Credentials
from vertexai.language_models import TextGenerationModel

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


def google_translate(text: str, client, target_language_code: str = "zh-CN"):
    """Translating Text."""
    if text is None or text == "":
        return text  # type: ignore

    # Must be 'us-central1' or 'global'.
    parent = f"projects/{project}/locations/global"

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


def generate_word_memory_tip(word):
    """
    生成单词记忆提示的函数。

    参数：
    word (str)：需要生成记忆提示的单词。

    返回值：
    str：生成的记忆提示文本。
    """
    parameters = {
        "candidate_count": 1,
        "max_output_tokens": 120,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 40,
    }
    model = TextGenerationModel.from_pretrained("text-bison")
    response = model.predict(
        f"""您是一名英语单词记忆专家，擅长根据单词特点指导记忆方法。请您为以下单词提供记忆提示，
备注：
1. 不要单独再显示单词、词性、释义；
2. 有必要时，请使用换行符；

输出"markdown"格式。

单词："{word}"
""",
        **parameters,
    )
    return response.text


def generate_english_topics(target, category, level, n=5):
    parameters = {
        "candidate_count": 1,
        "max_output_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 40,
    }
    model = TextGenerationModel.from_pretrained("text-bison")
    response = model.predict(
        f"""在指定领域内，生成{n}个话题。
学生当前英语水平：CEFR 分级 {level}
领域：{category}
目标：{target}
要求：
1. 话题要广泛；
2. 话题要贴近学生的实际生活，让学生有话可说；
3. 话题要有一定的开放性，让学生有充分的发挥空间；
4. 避免过于简单或复杂的话题；
5. 避免过于敏感或有争议的话题；
6. 话题的用词要根据学生的英语水平进行选择，以确保学生能够理解。
""",
        **parameters,
    )
    # 输出列表
    return response.text.splitlines()
