# from twilio.rest import Client
import logging
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

import streamlit as st
from cachetools import TTLCache
from faker import Faker
from pymongo import ASCENDING, IndexModel, MongoClient

from .constants import FAKE_EMAIL_DOMAIN
from .db_model import (
    LoginEvent,
    Payment,
    PaymentStatus,
    PurchaseType,
    TokenUsageRecord,
    User,
    UserRole,
    str_to_enum,
)
from .st_utils import get_firestore_client

# 创建或获取logger对象
logger = logging.getLogger("streamlit")


PRICES = {
    PurchaseType.ANNUAL: 6570,
    PurchaseType.QUARTERLY: 1890,
    PurchaseType.MONTHLY: 720,
    PurchaseType.WEEKLY: 210,
    PurchaseType.DAILY: 30,
}


class GoogleDbInterface:
    def __init__(self):
        self.faker = Faker("zh_CN")
        self.client = get_firestore_client()
        self.db = get_firestore_client()
        self.cache = TTLCache(maxsize=1000, ttl=86400)  # 24 hours cache
        # self.users.create_index([("phone_number", ASCENDING)], unique=True)
        # # self.users.create_index([("f_email", ASCENDING)], unique=True)
        # self.payments.create_index(
        #     [
        #         ("phone_number", ASCENDING),
        #         ("payment_id", ASCENDING),
        #         ("expiry_time", ASCENDING),
        #     ],
        #     unique=True,
        # )
        # self.words.create_index([("word", ASCENDING)], unique=True)

    # region 用户管理

    def register_user(self, user: User):
        doc_ref = self.db.collection("users").document()
        user_data = user.model_dump()
        doc_ref.set(user_data)

    # endregion
