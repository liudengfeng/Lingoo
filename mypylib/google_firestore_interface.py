# from twilio.rest import Client
import logging
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

import streamlit as st
from cachetools import TTLCache
from faker import Faker
from google.cloud import firestore
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

    def cache_user(self, user):
        phone_number = user.phone_number
        self.cache[phone_number] = {
            "status": "success",
            "display_name": user.display_name,
            "email": user.email,
            "user_role": user.user_role,
        }

    # region 用户管理

    def get_user(self, phone_number: str):
        doc_ref = self.db.collection("users").document(phone_number)
        doc = doc_ref.get()
        if doc.exists:
            user_data = doc.to_dict()
            user_data["phone_number"] = phone_number  # 添加手机号码
            return User.from_doc(user_data)
        else:
            return None

    def update_user(self, user: User):
        phone_number = user.phone_number
        doc_ref = self.db.collection("users").document(phone_number)
        user_data = user.model_dump()
        del user_data["phone_number"]  # 删除手机号码
        doc_ref.update(user_data)

    def register_user(self, user: User):
        phone_number = user.phone_number
        doc_ref = self.db.collection("users").document(phone_number)
        user_data = user.model_dump()
        del user_data["phone_number"]  # 删除手机号码
        doc_ref.set(user_data)

    # endregion

    # region 登录管理

    def create_login_event(self, phone_number):
        # 创建一个登录事件
        session_id = str(uuid.uuid4())
        login_events_ref = self.db.collection("login_events")
        login_event_doc_ref = login_events_ref.document(session_id)
        login_event_doc_ref.set(
            {
                "phone_number": phone_number,
                "login_time": datetime.now(timezone.utc),
                "logout_time": None,
            }
        )
        return session_id

    def login(self, phone_number, password):
        # 在缓存中查询是否已经正常登录
        if (
            phone_number in self.cache
            and self.cache[phone_number].get("status", "") == "success"
        ):
            return {"status": "warning", "message": "您已登录"}
        # 检查用户的凭据
        users_ref = self.db.collection("users")
        try:
            user_doc_ref = users_ref.document(phone_number)
            user_doc = user_doc_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_data["phone_number"] = phone_number  # 添加手机号码
                user = User.from_doc(user_data)
            else:
                raise Exception("用户不存在")
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
        except Exception as e:
            # st.write(e)
            return {
                "status": "error",
                "message": "无效的手机号码，或者密码无效。请展开下面的帮助文档，查看如何注册账号或重置密码。",
            }

    # endregion

    def logout(self, user_info, session_id):
        # 从缓存中删除用户的登录状态
        if user_info["phone_number"] in self.cache:
            del self.cache[user_info["phone_number"]]

        # 更新指定的登录事件
        login_events_ref = self.db.collection("login_events")
        login_event_doc_ref = login_events_ref.document(session_id)
        login_event_doc = login_event_doc_ref.get()
        if (
            login_event_doc.exists
            and login_event_doc.to_dict()["phone_number"] == user_info["phone_number"]
        ):
            login_event_doc_ref.update({"logout_time": datetime.utcnow()})

        return "Logout successful"

    # enddregion

    # region 角色管理

    # def is_admin(self, user_info: dict):
    #     if len(user_info) == 0:
    #         return False
    #     # 在缓存中查询用户是否已经正常登录
    #     phone_number = user_info["phone_number"]
    #     if phone_number in self.cache and self.cache[phone_number]:
    #         # 检查用户是否为管理员
    #         users_ref = self.db.collection("users")
    #         user_docs = users_ref.where("phone_number", "==", phone_number).stream()
    #         if user_docs:
    #             user_doc = next(user_docs).to_dict()
    #             # 创建一个User实例
    #             user = User.from_doc(user_doc)
    #             # 检查permission属性
    #             if user.user_role == UserRole.ADMIN:
    #                 return True
    #     return False

    def is_vip_or_admin(self, user_info: dict):
        # 在缓存中查询用户是否已经正常登录
        phone_number = user_info["phone_number"]
        if phone_number in self.cache and self.cache[phone_number]:
            # 检查用户是否为 VIP 或管理员
            users_ref = self.db.collection("users")
            user_docs = users_ref.where("phone_number", "==", phone_number).stream()
            if user_docs:
                user_doc = next(user_docs).to_dict()
                # 创建一个User实例
                user = User.from_doc(user_doc)
                # 检查permission属性
                if user.user_role in [UserRole.ADMIN, UserRole.VIP]:
                    return True
        return False

    # endregion

    # region 个人词库管理

    def find_personal_dictionary(self, phone_number):
        users_ref = self.db.collection("users")
        user_docs = users_ref.where("phone_number", "==", phone_number).stream()
        if user_docs:
            user_doc = next(user_docs).to_dict()
            return user_doc.get("personal_vocabulary", [])
        else:
            return []

    def add_word_to_personal_dictionary(self, phone_number, word):
        users_ref = self.db.collection("users")
        user_docs = users_ref.where("phone_number", "==", phone_number).stream()
        if user_docs:
            user_doc_ref = next(user_docs).reference
            user_doc = user_doc_ref.get().to_dict()
            personal_vocabulary = user_doc.get("personal_vocabulary", [])
            if word not in personal_vocabulary:
                personal_vocabulary.append(word)
                user_doc_ref.update({"personal_vocabulary": personal_vocabulary})

    def remove_word_from_personal_dictionary(self, phone_number, word):
        users_ref = self.db.collection("users")
        user_docs = users_ref.where("phone_number", "==", phone_number).stream()
        if user_docs:
            user_doc_ref = next(user_docs).reference
            user_doc = user_doc_ref.get().to_dict()
            personal_vocabulary = user_doc.get("personal_vocabulary", [])
            if word in personal_vocabulary:
                personal_vocabulary.remove(word)
                user_doc_ref.update({"personal_vocabulary": personal_vocabulary})

    # endregion

    # region token

    def get_token_count(self, phone_number):
        users_ref = self.db.collection("users")
        user_docs = users_ref.where("phone_number", "==", phone_number).stream()
        first_user_doc = next(user_docs, None)
        if first_user_doc:
            user_doc = first_user_doc.to_dict()
            return user_doc.get("total_tokens", 0)
        else:
            return 0

    def add_token_record(self, phone_number, token_type, used_token_count):
        used_token = TokenUsageRecord(
            token_type=token_type,
            used_token_count=used_token_count,
            used_at=datetime.now(tz=timezone.utc),
            phone_number=phone_number,
        )

        # 添加 token 记录到 'token_records' 集合
        token_records_ref = self.db.collection("token_records")
        token_records_ref.add(used_token.model_dump())

        # 更新用户的 'total_tokens' 属性
        users_ref = self.db.collection("users")
        user_docs = users_ref.where("phone_number", "==", phone_number).stream()
        first_user_doc = next(user_docs, None)
        if first_user_doc:
            user_doc_ref = first_user_doc.reference
            user_doc = user_doc_ref.get().to_dict()
            total_tokens = user_doc.get("total_tokens", 0)
            total_tokens += used_token_count
            user_doc_ref.update({"total_tokens": total_tokens})

    # endregion

    # region 支付管理

    def update_payment(self, phone_number, order_id, update_fields: dict):
        result = self.payments.update_one(
            {"phone_number": phone_number, "order_id": order_id},
            {"$set": update_fields},
        )
        # print(f"Update result: {result.raw_result}")
        return result.modified_count

    def is_service_active(self, user_info: dict):
        if len(user_info) == 0:
            return False
        # 查询用户
        user = self.users.find_one({"_id": user_info["user_id"]})
        # 如果用户是管理员，直接返回True
        if user and user["user_role"] == "管理员":
            return True
        # 查询用户的所有支付记录
        payments = self.payments.find({"phone_number": user_info["phone_number"]})
        # 遍历所有支付记录
        now = datetime.now(timezone.utc)
        for payment in payments:
            # 如果找到一条已经被批准且服务尚未到期的记录，返回True
            expiry_time = payment["expiry_time"].replace(tzinfo=timezone.utc)
            if payment["is_approved"] and expiry_time > now:
                return True
        # 如果没有找到符合条件的记录，返回False
        return False

    def enable_service(self, phone_number: str, order_id: str, purchase_type: str):
        # 查询用户的最后一个订阅记录
        payments_ref = self.db.collection("payments")
        payments_query = (
            payments_ref.where("phone_number", "==", phone_number)
            .where("status", "==", PaymentStatus.IN_SERVICE)
            .order_by("expiry_time", direction=firestore.Query.DESCENDING)
        )
        last_subscription_docs = payments_query.stream()
        last_subscription = next(last_subscription_docs, None)

        # 创建一个包含时区信息的 datetime 对象
        now = datetime.now(timezone.utc)
        base_time = now
        # 如果存在未过期的订阅，以其到期时间为基准
        if last_subscription is not None:
            last_subscription = last_subscription.to_dict()
            last_subscription_expiry_time = last_subscription["expiry_time"].replace(
                tzinfo=timezone.utc
            )
            if last_subscription_expiry_time > now:
                base_time = last_subscription_expiry_time

        # 将字符串转换为 PurchaseType 枚举
        purchase_type = str_to_enum(purchase_type, PurchaseType)  # type: ignore
        expiry_time = base_time + self.calculate_expiry(purchase_type)  # type: ignore

        # 更新支付记录的状态和到期时间
        payment_docs = (
            payments_ref.where("phone_number", "==", phone_number)
            .where("order_id", "==", order_id)
            .stream()
        )
        payment_doc = next(payment_docs, None)
        if payment_doc:
            payment_doc_ref = payment_doc.reference
            payment_doc_ref.update(
                {
                    "is_approved": True,
                    "expiry_time": expiry_time,
                    "status": PaymentStatus.IN_SERVICE,
                }
            )

    def calculate_expiry(self, purchase_type: PurchaseType):
        if purchase_type == PurchaseType.DAILY:
            return timedelta(days=1)
        elif purchase_type == PurchaseType.WEEKLY:
            return timedelta(days=7)
        elif purchase_type == PurchaseType.MONTHLY:
            return timedelta(days=30)
        elif purchase_type == PurchaseType.QUARTERLY:
            return timedelta(days=90)
        elif purchase_type == PurchaseType.ANNUAL:
            return timedelta(days=365)
        else:
            return timedelta(days=0)

    def add_payment(self, payment: Payment):
        phone_number = payment.phone_number
        users_ref = self.db.collection("users")
        user_docs = users_ref.where("phone_number", "==", phone_number).stream()
        first_user_doc = next(user_docs, None)
        if not first_user_doc:
            # 如果用户不存在，则创建一个新用户
            new_user = User(
                phone_number=phone_number,
                username=self.faker.user_name(),
                email=f"{phone_number}@{FAKE_EMAIL_DOMAIN}",
                password=phone_number,
                registration_time=datetime.now(timezone.utc),
                memo=f"订单号：{payment.order_id}",
            )  # type: ignore
            new_user.hash_password()
            self.register_user(new_user)

        if payment.receivable == payment.payment_amount:
            # 如果支付成功，更新用户的权限
            self.enable_service(phone_number, payment.order_id, payment.purchase_type)
            payment.status = PaymentStatus.IN_SERVICE
        # 添加支付记录
        payments_ref = self.db.collection("payments")
        payments_ref.add(payment.model_dump())

    # endregion

    # region 会话管理

    def get_active_sessions(self, phone_number: str):
        login_events_ref = self.db.collection("login_events")
        login_events_query = (
            login_events_ref.where("phone_number", "==", phone_number)
            .where("logout_time", "==", None)
            .order_by("login_time", direction=firestore.Query.DESCENDING)
        )
        login_events_docs = login_events_query.stream()
        active_sessions = [doc.to_dict() for doc in login_events_docs]
        if len(active_sessions) > 1:
            return active_sessions[:-1]  # 返回除最后一个登录事件外的所有未退出的登录事件
        return []

    def force_logout_session(self, phone_number: str, session_id: str):
        login_events_ref = self.db.collection("login_events")
        login_event_doc_ref = login_events_ref.document(session_id)
        login_event_doc = login_event_doc_ref.get()
        if (
            login_event_doc.exists
            and login_event_doc.to_dict()["phone_number"] == phone_number
        ):
            login_event_doc_ref.update({"logout_time": datetime.now(timezone.utc)})

    # endregion
