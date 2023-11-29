import json
from pathlib import Path

import google.generativeai as palm
import streamlit as st
import vertexai
from vertexai.language_models import TextGenerationModel

from mypylib.google_palm import (
    lookup,
)
from mypylib.google_api import get_translation_client, google_translate
from mypylib.google_api import init_vertex

current_cwd: Path = Path(__file__).parent.parent  # type: ignore
# model = "models/text-bison-001"

palm.configure(api_key=st.secrets["Google"]["PALM_API_KEY"])

if "google_tranlator" not in st.session_state:
    st.session_state["google_tranlator"] = get_translation_client(st.secrets)


def generate_text(word: str, level: str):
    # vertexai.init(project="lingo-406201", location="asia-northeast1")
    parameters = {
        "candidate_count": 1,
        "max_output_tokens": 1024,
        "temperature": 0.5,
        "top_p": 0.5,
        "top_k": 20,
    }

    prompt = f"""As an experienced English instructor who is proficient in CEFR graded vocabulary, you will be tasked with designing questions based on your students\' proficiency levels to assess their understanding of specific words or phrases.

    Require:
    1. Structure: The output should contain four distinct components: question, options, correct answer, and explanation.
    2. Language: Question stems and options should be presented in English.
    3. Clarity and Appropriateness: The language used in the question stem and options should be consistent with the student’s current level of English understanding.
    4. Concise language: The language is concise and clear, avoiding overly complex sentence structures or obscure vocabulary.
    5. Contextualization: Questions should be contextualized to help students grasp the meaning of the target word or phrase.
    6. Option Relevance: Options should be relevant to the question stem.
    7. Option Distribution: Out of the four options provided, only one should represent the correct answer, while the remaining three serve as incorrect options. The order of correct answers should be randomized to avoid predictability.
    8. Option identification: Each option must be clearly identified using a capital letter A, B, C, or D, separated from the option content by a period.
    9. Answer markings: Correct answers are marked A, B, C and D.
    10. Answer Explanation: In addition to stating the rationale behind the correct answer, if necessary, provide an explanation to clarify why other options are incorrect.
    11. Output format: The final output should follow the JSON format, using the \"Question\", \"Option\", \"Answer\" and \"Explanation\" keys to represent the corresponding components.

    Please answer a multiple-choice question based on the following information:
    Student’s current level: {level}
    Word: {word}"""

    model = TextGenerationModel.from_pretrained("text-bison")
    response = model.predict(
        prompt,
        **parameters,
    )
    return response.text


if "inited_vertex" not in st.session_state:
    init_vertex(st.secrets)
    st.session_state["inited_vertex"] = True

levels = ["A1", "A2", "B1", "B2", "C1", "C2"]
level = st.sidebar.selectbox("选择等级", levels)
st.text_input("输入", key="input", value="hello world")

if st.button("执行"):
    word = st.session_state["input"]
    cn = google_translate(word, st.session_state["google_tranlator"])
    d = lookup(st.session_state["input"])
    st.write(cn)
    st.write(d)

    # with open(current_cwd / "resource" / f"{word}.json", "w", encoding="utf-8") as f:  # type: ignore
    #     json.dump(d, f, ensure_ascii=False, indent=4)
    # st.write(generate_text(word, level))  # type: ignore

if st.button("测试"):
    word = st.session_state["input"]
    st.write(generate_text(word, level))  # type: ignore
