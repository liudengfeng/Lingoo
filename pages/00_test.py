import mimetypes
from pathlib import Path

import streamlit as st

# from PIL import Image
from vertexai.preview.generative_models import Part
from vertexai.preview.generative_models import Image as GImage
from google.oauth2.service_account import Credentials
from mypylib.google_cloud_configuration import vertexai_configure
from mypylib.st_utils import (
    authenticate_and_configure_services,
    google_translate,
    load_vertex_model,
    get_firestore_client,
)


CURRENT_CWD: Path = Path(__file__).parent.parent

st.set_page_config(page_title="Streamlit test", layout="centered", page_icon="🧊")
# authenticate_and_configure_services()
# vertexai_configure(st.secrets)
# import vertexai

st.header("FireStore", divider="rainbow")


# The `project` parameter is optional and represents which project the client
# will act on behalf of. If not supplied, the client falls back to the default
# project inferred from the environment.
db = get_firestore_client()


if st.button("提交", key="2"):
    doc_ref = db.collection("words").document("he/she")
    doc_ref.set({"first": "Ada", "last": "Lovelace", "born": 1815})


xx = """
st.tabs
Streamlit Version
Version 1.29.0
Insert containers separated into tabs.

Inserts a number of multi-element containers as tabs. Tabs are a navigational element that allows users to easily move between groups of related content.

To add elements to the returned containers, you can use "with" notation (preferred) or just call methods directly on the returned object. See examples below.

Warning

All the content of every tab is always sent to and rendered on the frontend. Conditional rendering is currently not supported.
"""

st.subheader(":bento: 1", anchor="1")
st.markdown(xx)
st.subheader(":bento: 2", anchor="2")
st.markdown(xx)
st.subheader(":bento: 3", anchor="3")
st.markdown(xx)
