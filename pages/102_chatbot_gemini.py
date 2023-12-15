import streamlit as st

import vertexai
from vertexai.preview.generative_models import GenerativeModel, Part
import time
from mypylib.streamlit_helper import authenticate

authenticate(st)


# def multiturn_generate_content():
#     config = {"max_output_tokens": 2048, "temperature": 0.9, "top_p": 1}
#     model = GenerativeModel("gemini-pro")
#     chat = model.start_chat()
#     response = chat.send_message("""你好""", generation_config=config)
#     st.write(response["usage_metadata"]["total_token_count"])  # type: ignore


# multiturn_generate_content()
