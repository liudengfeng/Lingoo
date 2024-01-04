from typing import List, Optional, Union

import streamlit as st
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel, Part

from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS


def generate_content(
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

    # 令牌数
    st.session_state.current_token_count = model.count_tokens(contents).total_tokens
    # 添加记录到数据库
    st.session_state.dbi.add_token_record(
        st.session_state.user_info["phone_number"],
        "gemini-pro-vision",
        st.session_state.current_token_count,
    )
    st.session_state.total_token_count += st.session_state.current_token_count
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}"
    )
