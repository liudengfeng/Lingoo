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
from .google_db_model import (
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

    def cache_user(self, user):
        phone_number = user.phone_number
        self.cache[phone_number] = {
            "display_name": user.display_name,
            "email": user.email,
            "user_role": user.user_role,
        }

    # region 用户管理

    def register_user(self, user: User):
        doc_ref = self.db.collection("users").document()
        user_data = user.model_dump()
        doc_ref.set(user_data)

    # endregion

    # region 登录管理

    def create_login_event(self, phone_number):
        # 创建一个登录事件
        session_id = str(uuid.uuid4())
        login_event = LoginEvent(session_id=session_id, phone_number=phone_number)

        # 获取login_events集合的引用
        login_events_ref = self.db.collection("login_events")

        # 在login_events集合中创建一个新的文档
        login_events_ref.add(login_event.model_dump())

        return session_id

    def login(self, phone_number, password):
        # 在缓存中查询是否已经正常登录 TODO：缓存内容
        if phone_number in self.cache and self.cache[phone_number]:
            return {"status": "warning", "message": "您已登录"}
        # 检查用户的凭据
        users_ref = self.db.collection("users")
        st.write(phone_number)
        # try:
        user_docs = users_ref.where("phone_number", "==", phone_number).stream()
        if user_docs:
            first_user_doc = next(user_docs).to_dict()
        else:
            first_user_doc = None
        # 创建一个User实例
        user = User.from_doc(first_user_doc)
        # 验证密码
        if user.check_password(password):
            # 如果密码正确，将用户的登录状态存储到缓存中
            self.cache_user(user)
            session_id = self.create_login_event(phone_number)
            return {
                "display_name": user.display_name,
                "session_id": session_id,
                "status": "success",
                "message": f"嗨！{user.display_name}，又见面了。",
            }
        # except Exception as e:
        #     st.write(e)
        #     return {
        #         "status": "error",
        #         "message": "无效的手机号码，或者密码无效。请展开下面的帮助文档，查看如何注册账号或重置密码。",
        #     }

    # endregion

    def logout(self, user_info):
        # 从缓存中删除用户的登录状态
        if user_info["phone_number"] in self.cache:
            del self.cache[user_info["phone_number"]]

        # 找到最近的登录事件
        login_events_ref = self.db.collection("login_events")
        login_events_docs = login_events_ref.where(
            "phone_number", "==", user_info["phone_number"]
        ).stream()

        last_login_event = None
        last_login_event_doc_ref = None
        for doc in login_events_docs:
            event = LoginEvent.from_doc(doc.to_dict())
            if (
                last_login_event is None
                or event.login_time > last_login_event.login_time
            ):
                last_login_event = event
                last_login_event_doc_ref = doc.reference

        if last_login_event:
            # 设置登出时间
            last_login_event.logout_time = datetime.utcnow()
            # 更新数据库中的特定登录事件
            last_login_event_doc_ref.update(
                {"logout_time": last_login_event.logout_time}
            )

        return "Logout successful"

    # enddregion
