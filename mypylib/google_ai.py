import json
import time
from typing import Callable, List

import streamlit as st
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel, Part

from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS


def display_generated_content_and_update_token(
    item_name: str,
    model: GenerativeModel,
    contents: List[Part],
    generation_config: GenerationConfig,
    stream: bool,
    placeholder,
):
    responses = model.generate_content(
        contents,
        generation_config=generation_config,
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        stream=stream,
    )
    full_response = ""
    total_tokens = 0
    # 提取生成的内容
    if stream:
        for chunk in responses:
            try:
                full_response += chunk.text
                total_tokens += chunk._raw_response.usage_metadata.total_token_count
                # st.write(f"流式块 令牌数：{chunk._raw_response.usage_metadata}")
            except (IndexError, ValueError) as e:
                st.write(chunk)
                st.error(e)
            time.sleep(0.05)
            # Add a blinking cursor to simulate typing
            placeholder.markdown(full_response + "▌")
    else:
        full_response = responses.text
        total_tokens += responses._raw_response.usage_metadata.total_token_count
        # st.write(f"responses 令牌数：{responses._raw_response.usage_metadata}")

    placeholder.markdown(full_response)

    # 添加记录到数据库
    st.session_state.dbi.add_token_record(
        st.session_state.dbi.cache["phone_number"], item_name, total_tokens
    )
    # 修改会话中的令牌数
    st.session_state.current_token_count = total_tokens
    st.session_state.total_token_count += total_tokens


def parse_generated_content_and_update_token(
    item_name: str,
    model: GenerativeModel,
    contents: List[Part],
    generation_config: GenerationConfig,
    stream: bool,
    parser: Callable,
):
    responses = model.generate_content(
        contents,
        generation_config=generation_config,
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        stream=stream,
    )
    full_response = ""
    total_tokens = 0
    # 提取生成的内容
    if stream:
        for chunk in responses:
            try:
                full_response += chunk.text
                total_tokens += chunk._raw_response.usage_metadata.total_token_count
            except (IndexError, ValueError) as e:
                st.write(chunk)
                st.error(e)
    else:
        full_response = responses.text
        total_tokens += responses._raw_response.usage_metadata.total_token_count

    # 添加记录到数据库
    st.session_state.dbi.add_token_record(
        st.session_state.dbi.cache["phone_number"], item_name, total_tokens
    )
    # 修改会话中的令牌数
    st.session_state.current_token_count = total_tokens
    st.session_state.total_token_count += total_tokens
    return parser(full_response)


WORD_IMAGE_PROMPT_TEMPLATE = """
你的任务是分步找出最能解释单词含义的前4张图片序号：
图片按输入顺序编号，序号从0开始。
第一步：按解释程度评分，最低0分，最高1.0。评分越高，图片越能解释单词的含义；
第二步：逐项分析是否满足以下条件，如果满足，每项加0.1分；
- 图片的清晰度和可读性是最重要的，用户应该能够轻松地理解图片所传达的信息。
- 图片应该准确地反映单词的含义，避免出现误导或混淆。
- 图片应该生动形象，能够引起用户的注意力和兴趣，从而促进对单词的理解和记忆。
- 图片的主题应该与单词的含义相关，能够帮助用户理解单词的具体含义。
- 图片的构图应该合理，能够突出单词的重点内容。
- 图片的色彩应该鲜明，能够引起用户的注意力。
第三步：剔除包含色情、暴力、毒品等内容或者得分少于0.6的序号；
第四步：按得分从高到低排序，选择前4张图片的序号；

输出python list格式。

单词：{word}
"""


def select_best_images_for_word(model, word, images: List[Part]):
    """
    为给定的单词选择最佳解释单词含义的图片。

    这个函数使用模型生成一个图片选择结果，然后返回最能解释给定单词含义的图片的序号列表。

    Args:
        word (str): 要解释的单词。
        images (List[Part]): 图片列表，每个元素都是一个Part对象，代表一张图片。
        model (GenerativeModel): 用于生成图片选择结果的模型。

    Returns:
        list: 以JSON格式输出的最佳图片序号列表。这些序号对应于输入的图片列表中的位置。如果没有合适的图片，则返回空列表。
    """
    prompt = WORD_IMAGE_PROMPT_TEMPLATE.format(word=word)
    contents = [Part.from_text(prompt)] + images
    generation_config = GenerationConfig(
        max_output_tokens=2048, temperature=0.1, top_p=1, top_k=32
    )
    return parse_generated_content_and_update_token(
        "挑选图片",
        model,
        contents,
        generation_config,
        stream=False,
        parser=lambda x: json.loads(x.replace("```python", "").replace("```", "")),
    )
