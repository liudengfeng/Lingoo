import streamlit as st
import vertexai
from vertexai.preview.language_models import TextGenerationModel

vertexai.init(
    project=st.secrets["Google"]["PROJECT_ID"],
    location=st.secrets["Google"]["LOCATION"],
)


@st.cache_resource
def get_generation_model():
    model = TextGenerationModel.from_pretrained("text-bison")
    return model


@st.cache_resource
def get_chat_model():
    model = TextGenerationModel.from_pretrained("chat-bison")
    return model


def get_text_generation(prompt, **parameters):
    model = get_generation_model()
    response = model.predict(prompt=prompt, **parameters)
    return response.text, model.count_tokens(response.text).total_billable_characters
