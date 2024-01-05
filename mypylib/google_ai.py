from typing import List, Optional, Union

import streamlit as st
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel, Part

from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS


def generate_content_and_update_token_count(
    item_name: str,
    sidebar_status: st.sidebar,
    model: GenerativeModel,
    contents: List[Part],
    generation_config: GenerationConfig,
    stream=False,
):
    responses = model.generate_content(
        contents,
        generation_config=generation_config,
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        stream=stream,
    )
    text = ""
    # 提取生成的内容
    if stream:
        for response in responses:
            text += response.text
    else:
        text = responses.text
    # 合成统计信息
    to_be_counted = [Part.from_text(text)] + contents
    # 令牌数
    st.session_state.current_token_count = model.count_tokens(
        to_be_counted
    ).total_tokens
    # 添加记录到数据库
    st.session_state.dbi.add_token_record(
        st.session_state.dbi.cache["phone_number"],
        item_name,
        st.session_state.current_token_count,
    )
    st.session_state.total_token_count += st.session_state.current_token_count
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}"
    )
    return responses
