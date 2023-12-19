import google.generativeai as genai


def configure(st):
    GOOGLE_API_KEY = st.secrets["Google"]["GEMINI_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
