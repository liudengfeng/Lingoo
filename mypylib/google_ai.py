import json
import time
from typing import Callable, List

import streamlit as st
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel, Part

from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS


def _update_token_counts_and_db(
    model: GenerativeModel,
    full_response: str,
    contents: List[Part],
    item_name: str,
):
    cs0 = model.count_tokens(contents)
    cs1 = model.count_tokens([Part.from_text(full_response)])
    st.write(f"输入的令牌数：{cs0.total_tokens}")
    st.write(f"生成的令牌数：{cs1.total_tokens}")
    # 合成统计信息
    to_be_counted = [Part.from_text(full_response)] + contents
    cs = model.count_tokens(to_be_counted)
    st.write(f"本次生成的令牌数：{cs.total_tokens}")
    # 修改会话中的令牌数
    st.session_state.current_token_count = cs.total_tokens
    # 添加记录到数据库
    st.session_state.dbi.add_token_record(
        st.session_state.dbi.cache["phone_number"],
        item_name,
        st.session_state.current_token_count,
    )
    st.session_state.total_token_count += st.session_state.current_token_count


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
    st.write(f"responses 令牌数：{responses._raw_response.usage_metadata}")
    full_response = ""
    # 提取生成的内容
    if stream:
        for chunk in responses:
            try:
                full_response += chunk.text
            except (IndexError, ValueError) as e:
                st.write(chunk)
                st.error(e)
            time.sleep(0.05)
            # Add a blinking cursor to simulate typing
            placeholder.markdown(full_response + "▌")
    else:
        full_response = responses.text

    placeholder.markdown(full_response)

    _update_token_counts_and_db(model, full_response, contents, item_name)


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
    # 提取生成的内容
    if stream:
        for chunk in responses:
            try:
                full_response += chunk.text
            except (IndexError, ValueError) as e:
                st.write(chunk)
                st.error(e)
    else:
        full_response = responses.text

    _update_token_counts_and_db(model, full_response, contents, item_name)

    return parser(full_response)


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
    prompt = f"单词：{word}\n输入的图片是否能形象解释单词含义，挑选出最合适的前4张图片。结果用输入图片的自然序号（从0开始）列表表达，如果没有合适的，返回空列表。以JSON格式输出。"
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
        parser=lambda x: json.loads(x.replace("```json", "").replace("```", "")),
    )
