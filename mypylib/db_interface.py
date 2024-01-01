# from twilio.rest import Client
import logging
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

import streamlit as st
from bson import ObjectId
from cachetools import TTLCache
from faker import Faker
from pymongo import ASCENDING, IndexModel, MongoClient

from .constants import FAKE_EMAIL_DOMAIN
from .db_model import (
    LoginEvent,
    Payment,
    PaymentStatus,
    PurchaseType,
    User,
    UserRole,
    str_to_enum,
)

# 创建或获取logger对象
logger = logging.getLogger("streamlit")


PRICES = {
    PurchaseType.ANNUAL: 6570,
    PurchaseType.QUARTERLY: 1890,
    PurchaseType.MONTHLY: 720,
    PurchaseType.WEEKLY: 210,
    PurchaseType.DAILY: 30,
}


def get_mongodb_uri():
    env = st.secrets["env"]
    if env == "wsl2":
        return st.secrets["Microsoft"]["WSL2_CONNECTION_STRING"]
    elif env == "windows":
        return st.secrets["Microsoft"]["WIN_CONNECTION_STRING"]
    elif env == "streamlit":
        return st.secrets["Microsoft"]["COSMOS_CONNECTION_STRING"]
    elif env == "azure":
        return st.secrets["Microsoft"]["COSMOS_CONNECTION_STRING"]
    else:
        raise ValueError(f"Invalid environment: {env}")


class DbInterface:
    def __init__(self):
        mongodb_uri = get_mongodb_uri()
        self.faker = Faker("zh_CN")
        self.client = MongoClient(mongodb_uri)
        self.db = self.client["pg"]
        self.users = self.db["users"]
        self.payments = self.db["payments"]
        self.words = self.db["words"]
        self.cache = TTLCache(maxsize=1000, ttl=86400)  # 24 hours cache
        self.users.create_indexes(
            [
                ("phone_number", ASCENDING),
                ("email", ASCENDING),
            ],
            unique=True,
        )
        self.payments.create_index(
            [
                ("phone_number", ASCENDING),
                ("payment_id", ASCENDING),
                ("expiry_time", ASCENDING),
            ],
            unique=True,
        )
        self.words.create_index([("word", ASCENDING)], unique=True)

    # region 会话管理

    def get_active_sessions(self, user_id: ObjectId):
        user_doc = self.users.find_one({"_id": user_id})
        if user_doc:
            user = User.from_doc(user_doc)
            if (
                user.login_events is not None
            ):  # Add condition to check if login_events is not None
                active_sessions = [
                    event for event in user.login_events if event.logout_time is None
                ]
                if len(active_sessions) > 1:
                    return active_sessions[:-1]  # 返回除最后一个登录事件外的所有未退出的登录事件
        return []

    def force_logout_session(self, user_id: ObjectId, session_id: str):
        # assert isinstance(user_id, ObjectId)
        user_doc = self.users.find_one({"_id": user_id})
        if user_doc:
            user = User.from_doc(user_doc)
            for event in user.login_events:
                if event.session_id == session_id and event.logout_time is None:
                    event.logout_time = datetime.utcnow()
                    self.users.update_one(
                        {
                            "_id": user_id,
                            "login_events.session_id": session_id,
                        },
                        {"$set": {"login_events.$.logout_time": event.logout_time}},
                    )
                    break

    # endregion
    # region 用户管理
    def register_user(self, user: User):
        self.users.insert_one(user.model_dump())

    def find_user(self, user_id: ObjectId):
        # 查询数据库
        user = self.users.find_one({"_id": user_id})
        return user

    def find_user_by(self, phone=None, email=None):
        query = {}
        if phone:
            query["phone_number"] = phone
        if email:
            query["email"] = email

        user = self.users.find_one(query)
        return user

    def update_user(self, user_id: ObjectId, update_fields: dict):
        result = self.users.update_one(
            {"_id": user_id},
            {"$set": update_fields},
        )
        return result.modified_count

    # endregion

    # region 支付管理
    def update_payment(self, phone_number, order_id, update_fields: dict):
        result = self.payments.update_one(
            {"phone_number": phone_number, "order_id": order_id},
            {"$set": update_fields},
        )
        # print(f"Update result: {result.raw_result}")
        return result.modified_count

    # endregion

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
        last_subscription = self.payments.find_one(
            {"phone_number": phone_number, "status": PaymentStatus.IN_SERVICE},
            sort=[("expiry_time", -1)],
        )
        # 创建一个包含时区信息的 datetime 对象
        now = datetime.now(timezone.utc)
        base_time = now
        # 如果存在未过期的订阅，以其到期时间为基准
        if last_subscription is not None:
            last_subscription = last_subscription["expiry_time"].replace(
                tzinfo=timezone.utc
            )
            if last_subscription > now:
                base_time = last_subscription
        # 将字符串转换为 PurchaseType 枚举
        purchase_type = str_to_enum(purchase_type, PurchaseType)  # type: ignore
        expiry_time = base_time + self.calculate_expiry(purchase_type)  # type: ignore
        # Update the user info with approval status and expiration date
        update_fields = {}
        update_fields["is_approved"] = True
        update_fields["expiry_time"] = expiry_time
        update_fields["status"] = PaymentStatus.IN_SERVICE
        self.update_payment(phone_number, order_id, update_fields)

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
        user = self.users.find_one({"phone_number": phone_number})
        if not user:
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
        self.payments.insert_one(payment.model_dump())

    # def send_verification_code(self, phone_number: str):
    #     verification = self.twilio_client.verify.v2.services(
    #         st.secrets["TWILIO_VERIFY_SID"]
    #     ).verifications.create(to=phone_number, channel="sms")
    #     return verification.status

    # def verify_code(self, phone_number: str, code: str):
    #     verification_check = self.twilio_client.verify.v2.services(
    #         st.secrets["TWILIO_VERIFY_SID"]
    #     ).verification_checks.create(to=phone_number, code=code)
    #     return verification_check.status

    def generate_verification_code(self, identifier: str):
        # 生成一个6位数的验证码
        verification_code = "".join(random.choice(string.digits) for _ in range(6))
        # 更新用户的文档，添加验证码和生成时间
        self.users.update_one(
            {"$or": [{"phone_number": identifier}, {"email": identifier}]},
            {
                "$set": {
                    "verification_code": verification_code,
                    "verification_code_time": datetime.now(timezone.utc),
                }
            },
        )
        return verification_code

    def cache_user(self, user):
        user.set_secret_key(st.secrets["FERNET_KEY"].encode())
        phone_number = user.phone_number
        self.cache[phone_number] = {
            "user_id": user.user_id,
            "display_name": user.display_name,
            "email": user.email,
            "user_role": user.user_role,
        }

    # TODO：删除
    def login_with_verification_code(self, identifier: str, verification_code: str):
        # 查询用户
        user = self.users.find_one(
            {"$or": [{"phone_number": identifier}, {"email": identifier}]}
        )
        if user:
            # 检查验证码是否正确和有效
            if user.get("verification_code") == verification_code and datetime.now(
                timezone.utc
            ) - user.get("verification_code_time", datetime.min) <= timedelta(
                minutes=30
            ):
                # 如果登录成功，将用户添加到缓存
                self.cache_user(user)
                return "成功登录"
            else:
                return "Invalid verification code"
        else:
            return "Invalid phone number or email"

    def login(self, phone_number, password):
        # 在缓存中查询是否已经正常登录
        if phone_number in self.cache and self.cache[phone_number]:
            return {"status": "warning", "message": "您已登录"}
        # 检查用户的凭据
        user_doc = self.users.find_one({"phone_number": phone_number})
        if user_doc:
            # 创建一个User实例
            user = User.from_doc(user_doc)
            # 验证密码
            if user.check_password(password):
                # 如果密码正确，将用户的登录状态存储到缓存中
                self.cache_user(user)
                # 创建一个登录事件
                session_id = str(uuid.uuid4())
                login_event = LoginEvent(
                    session_id=session_id, login_time=datetime.now(timezone.utc)
                )
                # 更新数据库中的用户文档
                self.users.update_one(
                    {"_id": user.user_id},
                    {"$push": {"login_events": login_event.model_dump()}},
                )
                return {
                    "user_id": user.user_id,
                    "display_name": user.display_name,
                    "session_id": session_id,
                    "status": "success",
                    "message": f"嗨！{user.display_name}，又见面了。",
                }
        return {
            "status": "error",
            "message": "无效的手机号码，或者密码无效。请展开下面的帮助文档，查看如何注册账号或重置密码。",
        }

    def logout(self, user_info):
        # 从缓存中删除用户的登录状态
        if user_info["phone_number"] in self.cache:
            del self.cache[user_info["phone_number"]]
        # 查询用户的文档
        user_doc = self.users.find_one({"phone_number": user_info["phone_number"]})
        if user_doc:
            # 创建一个User实例
            user = User.from_doc(user_doc)
            # 找到最近的登录事件
            if user.login_events:
                last_login_event = max(
                    user.login_events, key=lambda event: event.login_time
                )
                # 设置登出时间
                last_login_event.logout_time = datetime.now(timezone.utc)
                # 更新数据库中的特定登录事件
                self.users.update_one(
                    {
                        "_id": user.user_id,
                        "login_events.session_id": last_login_event.session_id,
                    },
                    {
                        "$set": {
                            "login_events.$.logout_time": last_login_event.logout_time
                        }
                    },
                )
        return "Logout successful"

    def is_admin(self, user_info: dict):
        if len(user_info) == 0:
            return False
        # 在缓存中查询用户是否已经正常登录
        phone_number = user_info["phone_number"]
        if phone_number in self.cache and self.cache[phone_number]:
            # 检查用户是否为管理员
            user_doc = self.users.find_one({"phone_number": phone_number})
            if user_doc:
                # 创建一个User实例
                user = User.from_doc(user_doc)
                # 检查permission属性
                if user.user_role == UserRole.ADMIN:
                    return True
        return False

    def is_vip_or_admin(self, user_info: dict):
        # 在缓存中查询用户是否已经正常登录
        phone_number = user_info["phone_number"]
        if phone_number in self.cache and self.cache[phone_number]:
            # 检查用户是否为 VIP 或管理员
            user_doc = self.users.find_one({"phone_number": phone_number})
            if user_doc:
                # 创建一个User实例
                user = User.from_doc(user_doc)
                # 检查permission属性
                if user.user_role in [UserRole.ADMIN, UserRole.VIP]:
                    return True
        return False

    # region 个人词库管理

    def find_personal_dictionary(self, phone_number):
        user_doc = self.users.find_one({"phone_number": phone_number})
        if user_doc:
            return user_doc.get("personal_words", [])
        else:
            return []

    def add_word_to_personal_dictionary(self, phone_number, word):
        user_doc = self.users.find_one({"phone_number": phone_number})
        if user_doc:
            personal_words = user_doc.get("personal_words", [])
            if word not in personal_words:
                self.users.update_one(
                    {"phone_number": phone_number}, {"$push": {"personal_words": word}}
                )

    def remove_word_from_personal_dictionary(self, phone_number, word):
        self.users.update_one(
            {"phone_number": phone_number}, {"$pull": {"personal_words": word}}
        )

    # endregion

    # region 词库管理

    def find_word(self, word):
        word_data = self.words.find_one({"word": word})
        return word_data

    # endregion
