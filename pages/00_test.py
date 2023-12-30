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
    doc_ref = db.collection("users").document("alovelace")
    doc_ref.set({"first": "Ada", "last": "Lovelace", "born": 1815})
