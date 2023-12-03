import base64
import hashlib
import json
import os
import random
from io import BytesIO
from pathlib import Path

from gtts import gTTS

current_cwd: Path = Path(__file__).parent.parent


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


def audio_autoplay_elem(fp: str, controls: bool = False, fmt="mp3"):
    audio_type = "audio/mp3" if fmt == "mp3" else "audio/wav"
    with open(fp, "rb") as f:
        data = f.read()
        b64 = base64.b64encode(data).decode()
        if controls:
            return f"""\
                <audio controls autoplay>
                    <source src="data:{audio_type};base64,{b64}" type="{audio_type}">
                </audio>
                """
        else:
            return f"""\
                <audio autoplay>
                    <source src="data:{audio_type};base64,{b64}" type="{audio_type}">
                </audio>
                """


# def wav_autoplay_elem(wav_fp: str, controls: bool = False):
#     with open(wav_fp, "rb") as f:
#         data = f.read()
#         b64 = base64.b64encode(data).decode()
#         if controls:
#             return f"""\
#                 <audio controls autoplay>
#                     <source src="data:audio/wav;base64,{b64}" type="audio/wav">
#                 </audio>
#                 """
#         else:
#             return f"""\
#                 <audio autoplay>
#                     <source src="data:audio/wav;base64,{b64}" type="audio/wav">
#                 </audio>
#                 """


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
    fp = os.path.join(current_cwd, "resource", "dictionary", "cefr.json")
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
    fp = os.path.join(current_cwd, "resource", "dictionary", "cefr.json")
    with open(fp, "r") as f:
        cefr = json.load(f)
    return random.sample(cefr[level], n)
