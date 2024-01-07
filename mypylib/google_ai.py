import time
from typing import List, Optional, Union

import streamlit as st
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel, Part

from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS


def generate_content_and_update_token(
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

    # 合成统计信息
    to_be_counted = [Part.from_text(full_response)] + contents
    # 修改会话中的令牌数
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
