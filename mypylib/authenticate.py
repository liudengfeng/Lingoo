# from twilio.rest import Client
import random
import string
from datetime import datetime, timedelta

import streamlit as st
from cachetools import TTLCache
from faker import Faker
from pymongo import ASCENDING, IndexModel, MongoClient

from .db_model import Payment, PaymentStatus, User, PurchaseType, UserRole
from .constants import FAKE_EMAIL_DOMAIN

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
        # 检查集合是否存在，如果不存在则创建索引
        if "users" not in self.db.list_collection_names():
            self.users.create_indexes(
                [
                    IndexModel([("phone_number", ASCENDING)], unique=True),
                    IndexModel([("email", ASCENDING)], unique=True),
                ]
            )
        # 检查 payments 集合是否存在，如果不存在则创建索引
        if "payments" not in self.db.list_collection_names():
            self.payments.create_index(
                [("phone_number", ASCENDING), ("payment_id", ASCENDING)], unique=True
            )

        # 检查集合是否存在
        if "words" not in self.db.list_collection_names():
            # 集合不存在，创建集合和索引
            self.words.create_index([("word", ASCENDING)], unique=True)

    def register_user(self, user: User):
        user.hash_password()
        self.users.insert_one(user.model_dump())

    def find_user(self, phone_number=None, email=None):
        key = phone_number or email
        # 否则，查询数据库
        user = self.users.find_one(
            {"$or": [{"phone_number": phone_number}, {"email": email}]}
        )
        return user

    def update_payment(self, phone_number, order_id, update_fields: dict):
        # print(f"Updating user with identifier {identifier} and fields {update_fields}")
        result = self.payments.update_one(
            {"phone_number": phone_number, "order_id": order_id},
            {"$set": update_fields},
        )
        # print(f"Update result: {result.raw_result}")
        return result.modified_count

    def update_user(self, identifier, update_fields: dict):
        # print(f"Updating user with identifier {identifier} and fields {update_fields}")
        result = self.users.update_one(
            {"$or": [{"phone_number": identifier}, {"email": identifier}]},
            {"$set": update_fields},
        )
        # print(f"Update result: {result.raw_result}")
        return result.modified_count

    def is_service_active(self, phone_number):
        # 查询用户
        user = self.users.find_one({"phone_number": phone_number})
        # 如果用户是管理员，直接返回True
        if user and user["permission"] == "管理员":
            return True
        # 查询用户的所有支付记录
        payments = self.payments.find({"phone_number": phone_number})
        # 遍历所有支付记录
        for payment in payments:
            # 如果找到一条已经被批准且服务尚未到期的记录，返回True
            if payment["is_approved"] and payment["expiry_time"] > datetime.utcnow():
                return True
        # 如果没有找到符合条件的记录，返回False
        return False

    def enable_service(self, phone_number, order_id, purchase_type):
        expiry_time = datetime.utcnow() + self.calculate_expiry(purchase_type)
        # Update the user info with approval status and expiration date
        update_fields = {}
        update_fields["is_approved"] = True
        update_fields["expiry_time"] = expiry_time
        update_fields["status"] = PaymentStatus.IN_SERVICE
        # print(update_fields)
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
                password="12345678",
                registration_time=datetime.utcnow(),
                memo=f"订单号：{payment.order_id}",
            )  # type: ignore
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
                    "verification_code_time": datetime.utcnow(),
                }
            },
        )
        return verification_code

    def cache_user(self, user):
        # Add user to cache
        identifier = user["phone_number"] or user["email"]
        self.cache[identifier] = user

    def login_with_verification_code(self, identifier: str, verification_code: str):
        # 查询用户
        user = self.users.find_one(
            {"$or": [{"phone_number": identifier}, {"email": identifier}]}
        )
        if user:
            # 检查验证码是否正确和有效
            if user.get(
                "verification_code"
            ) == verification_code and datetime.utcnow() - user.get(
                "verification_code_time", datetime.min
            ) <= timedelta(
                minutes=30
            ):
                # 如果登录成功，将用户添加到缓存
                self.cache_user(user)
                return "Login successful"
            else:
                return "Invalid verification code"
        else:
            return "Invalid phone number or email"

    def send_email(self, to_email: str, subject: str, content: str):
        raise NotImplementedError

    def login(self, phone_number, password):
        # 在缓存中查询是否已经正常登录
        if phone_number in self.cache and self.cache[phone_number]:
            return "您已登录"
        # 检查用户的凭据
        user_data = self.users.find_one({"phone_number": phone_number})
        if user_data:
            # 创建一个User实例
            user = User(**user_data)
            # 验证密码
            if user.check_password(password):
                # 如果密码正确，将用户的登录状态存储到缓存中
                self.cache[phone_number] = True
                return "Login successful"
        return "无效的手机号码，或者密码无效。请展开下面的帮助文档，查看如何注册账号或重置密码。"

    def logout(self, phone_number):
        # 从缓存中删除用户的登录状态
        if phone_number in self.cache:
            del self.cache[phone_number]
        return "Logout successful"

    def is_admin(self, phone_number=None, email=None):
        # 在缓存中查询用户是否已经正常登录
        key = phone_number or email
        if key in self.cache and self.cache[key]:
            # 检查用户是否为管理员
            user_data = self.users.find_one(
                {"$or": [{"phone_number": phone_number}, {"email": email}]}
            )
            if user_data:
                # 创建一个User实例
                user = User(**user_data)
                # 检查permission属性
                if user.permission == UserRole.ADMIN:
                    return True
        return False

    def is_vip_or_admin(self, phone_number=None, email=None):
        # 在缓存中查询用户是否已经正常登录
        key = phone_number or email
        if key in self.cache and self.cache[key]:
            # 检查用户是否为 VIP 或管理员
            user_data = self.users.find_one(
                {"$or": [{"phone_number": phone_number}, {"email": email}]}
            )
            if user_data:
                # 创建一个User实例
                user = User(**user_data)
                # 检查permission属性
                if user.permission in [UserRole.ADMIN, UserRole.VIP]:
                    return True
        return False

    # region 个人词库管理

    def add_to_personal_dictionary(self, phone_number, word):
        self.users.update_one(
            {"phone_number": phone_number}, {"$push": {"personal_words": word}}
        )

    def remove_from_personal_dictionary(self, phone_number, word):
        self.users.update_one(
            {"phone_number": phone_number}, {"$pull": {"personal_words": word}}
        )

    # endregion

    # region 词库管理

    def find_word(self, word):
        word_data = self.words.find_one({"word": word})
        return word_data

    # endregion
