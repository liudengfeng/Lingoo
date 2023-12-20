import time

import google.generativeai as genai
import streamlit as st

from mypylib.google_gemini import configure

# import vertexai
# from vertexai.preview.generative_models import GenerativeModel, Part


configure(st)


# def multiturn_generate_content():
#     config = {"max_output_tokens": 2048, "temperature": 0.9, "top_p": 1}
#     model = GenerativeModel("gemini-pro")
#     chat = model.start_chat()
#     response = chat.send_message("""你好""", generation_config=config)
#     # st.write(response.usage_metadata.total_token_count)  # type: ignore
#     st.write(response.text)
#     total_token_count = response._raw_response.usage_metadata
#     st.write(total_token_count.total_token_count)


model = genai.GenerativeModel("gemini-pro")
response = model.generate_content("生活的意义是什么？")
st.markdown(response.text)
