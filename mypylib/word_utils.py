import base64
import hashlib
import json
import os
import random
from io import BytesIO
from pathlib import Path
from typing import Union

from azure.storage.blob import BlobClient, BlobServiceClient, ContainerClient
from gtts import gTTS

from .azure_speech import synthesize_speech_to_file

CURRENT_CWD: Path = Path(__file__).parent.parent


def hash_word(word: str):
    # 创建一个md5哈希对象
    hasher = hashlib.md5()

    # 更新哈希对象的状态
    # 注意，我们需要将字符串转换为字节串，因为哈希函数只接受字节串
    hasher.update(word.encode("utf-8"))

    # 获取哈希值
    hash_value = hasher.hexdigest()

    return hash_value


def get_word_cefr_map(name, fp):
    assert name in ("us", "uk"), "只支持`US、UK`二种发音。"
    with open(os.path.join(fp, f"{name}_cefr.json"), "r") as f:
        return json.load(f)


# def audio_autoplay_elem(fp: str, controls: bool = False, fmt="mp3"):
#     audio_type = "audio/mp3" if fmt == "mp3" else "audio/wav"
#     with open(fp, "rb") as f:
#         data = f.read()
#         b64 = base64.b64encode(data).decode()
#     if controls:
#         return f"""\
#             <audio controls autoplay>\
#                 <source src="data:{audio_type};base64,{b64}" type="{audio_type}">\
#                 Your browser does not support the audio element.\
#             </audio>\
#             <script>\
#                 var audio = document.querySelector('audio');\
#                 audio.load();\
#                 audio.play();\
#             </script>\
#             """
#     else:
#         return f"""\
#             <audio autoplay>\
#                 <source src="data:{audio_type};base64,{b64}" type="{audio_type}">\
#                 Your browser does not support the audio element.\
#             </audio>\
#             <script>\
#                 var audio = document.querySelector('audio');\
#                 audio.load();\
#                 audio.play();\
#             </script>\
#             """


def audio_autoplay_elem(data: Union[bytes, str], controls: bool = False, fmt="mp3"):
    audio_type = "audio/mp3" if fmt == "mp3" else "audio/wav"

    # 如果 data 是字符串，假定它是一个文件路径，并从文件中读取音频数据
    if isinstance(data, str):
        with open(data, "rb") as f:
            data = f.read()

    b64 = base64.b64encode(data).decode()
    if controls:
        return f"""\
<audio controls autoplay>\
    <source src="data:{audio_type};base64,{b64}" type="{audio_type}">\
    Your browser does not support the audio element.\
</audio>\
<script>\
    var audio = document.querySelector('audio');\
    audio.load();\
    audio.play();\
</script>\
            """
    else:
        return f"""\
<audio autoplay>\
    <source src="data:{audio_type};base64,{b64}" type="{audio_type}">\
    Your browser does not support the audio element.\
</audio>\
<script>\
    var audio = document.querySelector('audio');\
    audio.load();\
    audio.play();\
</script>\
            """


# def audio_autoplay_elem(fp: str, controls: bool = False, fmt="mp3"):
#     relative_path = os.path.relpath(fp, CURRENT_CWD)
#     # 如果当前操作系统是 Windows，将反斜杠替换为正斜杠
#     if os.name == "nt":
#         relative_path = relative_path.replace("\\", "/")
#     if controls:
#         return f"""\
#             <audio controls autoplay>\
#                 <source src="{relative_path}" type="audio/mpeg">\
#                 Your browser does not support the audio element.\
#             </audio>\
#             <script>\
#                 var audio = document.querySelector('audio');\
#                 audio.load();\
#                 audio.play();\
#             </script>\
#             """
#     else:
#         return f"""\
#             <audio autoplay>\
#                 <source src="{relative_path}" type="audio/mpeg">\
#                 Your browser does not support the audio element.\
#             </audio>\
#             <script>\
#                 var audio = document.querySelector('audio');\
#                 audio.load();\
#                 audio.play();\
#             </script>\
#             """


def gtts_autoplay_elem(text: str, lang: str, tld: str):
    tts = gTTS(text, lang=lang, tld=tld)
    io = BytesIO()
    tts.write_to_fp(io)
    b64 = base64.b64encode(io.getvalue()).decode()
    return f"""\
        <audio controls autoplay>
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
        """


def get_lowest_cefr_level(word):
    """
    Get the lowest CEFR level of a given word.

    Parameters:
    word (str): The word to check the CEFR level for.

    Returns:
    str or None: The lowest CEFR level of the word, or None if the word is not found in the CEFR dictionary.
    """
    fp = os.path.join(CURRENT_CWD, "resource", "dictionary", "cefr.json")
    levels = ["A1", "A2", "B1", "B2", "C1"]
    with open(fp, "r") as f:
        cefr = json.load(f)
    for level in levels:
        if word in cefr[level]:
            return level
    return None


def sample_words(level, n):
    """
    Generate a random sample of words from a specific CEFR level.

    Args:
        level (str): The CEFR level of the words. Must be one of ["A1", "A2", "B1", "B2", "C1"].
        n (int): The number of words to sample.

    Returns:
        list: A list of randomly sampled words from the specified CEFR level.
    """
    levels = ["A1", "A2", "B1", "B2", "C1"]
    assert level in levels, f"level must be one of {levels}"
    fp = os.path.join(CURRENT_CWD, "resource", "dictionary", "cefr.json")
    with open(fp, "r") as f:
        cefr = json.load(f)
    return random.sample(cefr[level], n)


# def get_or_create_audio_in_blob_storage(word: str, style: str, secrets: dict):
#     # 生成单词的哈希值
#     hash_value = hash_word(word)

#     # 生成单词的语音文件名
#     filename = f"e{hash_value}.mp3"

#     # 创建 BlobServiceClient 对象，用于连接到 Blob 服务
#     blob_service_client = BlobServiceClient.from_connection_string(
#         secrets["Microsoft"]["AZURE_STORAGE_CONNECTION_STRING"]
#     )

#     # 创建 ContainerClient 对象，用于连接到容器
#     container_client = blob_service_client.get_container_client("word-voices")

#     # 创建 BlobClient 对象，用于操作 Blob
#     blob_client = container_client.get_blob_client(f"{style}/{filename}")

#     # 如果 Blob 不存在，则调用 Azure 的语音合成服务生成语音文件，并上传到 Blob
#     if not blob_client.exists():
#         # 生成语音文件
#         synthesize_speech_to_file(
#             word,
#             filename,
#             secrets["Microsoft"]["SPEECH_KEY"],
#             secrets["Microsoft"]["SPEECH_REGION"],
#             style,  # type: ignore
#         )

#         # 上传文件到 Blob
#         with open(filename, "rb") as data:
#             blob_client.upload_blob(data)

#     # 返回 Blob 的 URL
#     return blob_client.url


def get_or_create_and_return_audio_data(word: str, style: str, secrets: dict):
    # 生成单词的哈希值
    hash_value = hash_word(word)

    # 生成单词的语音文件名
    filename = f"e{hash_value}.mp3"

    # 创建 BlobServiceClient 对象，用于连接到 Blob 服务
    blob_service_client = BlobServiceClient.from_connection_string(
        secrets["Microsoft"]["AZURE_STORAGE_CONNECTION_STRING"]
    )

    # 创建 ContainerClient 对象，用于连接到容器
    container_client = blob_service_client.get_container_client("word-voices")

    # 创建 BlobClient 对象，用于操作 Blob
    blob_client = container_client.get_blob_client(f"{style}/{filename}")

    # 如果 Blob 不存在，则调用 Azure 的语音合成服务生成语音文件，并上传到 Blob
    if not blob_client.exists():
        # 生成语音文件
        synthesize_speech_to_file(
            word,
            filename,
            secrets["Microsoft"]["SPEECH_KEY"],
            secrets["Microsoft"]["SPEECH_REGION"],
            style,  # type: ignore
        )

        # 上传文件到 Blob
        with open(filename, "rb") as data:
            blob_client.upload_blob(data)

    # 读取 Blob 的内容
    audio_data = blob_client.download_blob().readall()

    return audio_data
