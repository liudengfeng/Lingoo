import time

import google.generativeai as genai
import streamlit as st
from vertexai.preview.generative_models import ChatSession, GenerativeModel
from mypylib.streamlit_helper import authenticate, check_and_force_logout
from mypylib.google_gemini import configure

# import vertexai
# from vertexai.preview.generative_models import GenerativeModel, Part
# 注意 ：对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。
# response.usage_metadata.total_token_count

# region 页面设置

st.set_page_config(
    page_title="聊天机器人",
    page_icon="🤖",
    layout="wide",
)

# endregion

# region 边栏

st.sidebar.markdown(
    """:rainbow[运行设置]\n
🔯 模型：Gemini Pro            
"""
)
sidebar_status = st.sidebar.empty()

# endregion

authenticate(st)
check_and_force_logout(st, sidebar_status)

# def multiturn_generate_content():
#     config = {"max_output_tokens": 2048, "temperature": 0.9, "top_p": 1}
#     model = GenerativeModel("gemini-pro")
#     chat = model.start_chat()
#     response = chat.send_message("""你好""", generation_config=config)
#     # st.write(response.usage_metadata.total_token_count)  # type: ignore
#     st.write(response.text)
#     total_token_count = response._raw_response.usage_metadata
#     st.write(total_token_count.total_token_count)


# model = genai.GenerativeModel("gemini-pro")
# response = model.generate_content("生活的意义是什么？")
# st.markdown(response.text)
