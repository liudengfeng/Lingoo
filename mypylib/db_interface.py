import logging
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache
from faker import Faker
from google.cloud import firestore
from google.cloud.firestore import FieldFilter

from .constants import FAKE_EMAIL_DOMAIN
from .db_model import (
    Payment,
    PaymentStatus,
    PurchaseType,
    TokenUsageRecord,
    User,
)
from .st_helper import get_firestore_client

# 创建或获取logger对象
logger = logging.getLogger("streamlit")


PRICES = {
    PurchaseType.ANNUAL: 6570,
    PurchaseType.QUARTERLY: 1890,
    PurchaseType.MONTHLY: 720,
    PurchaseType.WEEKLY: 210,
    PurchaseType.DAILY: 30,
}


class DbInterface:
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
        # 为用户密码加密
        user.hash_password()
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
        user_doc_ref = users_ref.document(phone_number)
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            user_data["phone_number"] = phone_number  # 添加手机号码
            user = User.from_doc(user_data)
            # 验证密码
            if user.check_password(password):
                # 如果密码正确，将用户的登录状态存储到缓存中
                self.cache_user(user)
                session_id = self.create_login_event(phone_number)
                return {
                    "display_name": user.display_name,
                    "session_id": session_id,
                    "status": "success",
                    "user_role": user.user_role,
                    "timezone": user.timezone,
                    "message": f"嗨！{user.display_name}，又见面了。",
                }
            else:
                return {
                    "status": "error",
                    "message": "密码错误，请重新输入",
                }
        else:
            return {
                "status": "error",
                "message": f"不存在与手机号码 {phone_number} 相关联的用户",
            }

    def logout(self, user_info):
        # 从缓存中删除用户的登录状态
        if user_info["phone_number"] in self.cache:
            del self.cache[user_info["phone_number"]]

        login_events_ref = self.db.collection("login_events")
        login_events = (
            login_events_ref.where(
                filter=FieldFilter("phone_number", "==", user_info["phone_number"])
            )
            .where(filter=FieldFilter("logout_time", "==", None))
            .stream()
        )

        for login_event in login_events:
            login_event.reference.update({"logout_time": datetime.now(tz=timezone.utc)})

        return "Logout successful"

    # endregion

    # region 个人词库管理

    def find_personal_dictionary(self, phone_number):
        # 获取用户文档的引用
        user_doc_ref = self.db.collection("users").document(phone_number)
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return user_data.get("personal_vocabulary", [])
        else:
            return []

    def add_word_to_personal_dictionary(self, phone_number, word):
        # 获取用户文档的引用
        user_doc_ref = self.db.collection("users").document(phone_number)
        # 使用 arrayUnion 方法添加单词到个人词典
        user_doc_ref.update({"personal_vocabulary": firestore.ArrayUnion([word])})

    def remove_word_from_personal_dictionary(self, phone_number, word):
        # 获取用户文档的引用
        user_doc_ref = self.db.collection("users").document(phone_number)
        # 使用 arrayRemove 方法从个人词典中移除单词
        user_doc_ref.update({"personal_vocabulary": firestore.ArrayRemove([word])})

    # endregion

    # region token

    def get_token_count(self, phone_number):
        # 获取用户文档的引用
        user_doc_ref = self.db.collection("users").document(phone_number)
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return user_data.get("total_tokens", 0)
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
        token_records_ref.document(phone_number).set(used_token.model_dump())

        # 更新用户的 'total_tokens' 属性
        user_doc_ref = self.db.collection("users").document(phone_number)
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            total_tokens = user_data.get("total_tokens", 0)
            total_tokens += used_token_count
            user_doc_ref.update({"total_tokens": total_tokens})

    # endregion

    # region 支付管理

    def query_payments(self, query_dict: dict):
        # 检查所有的值是否有效
        invalid_keys = [key for key, value in query_dict.items() if value is None]
        if invalid_keys:
            raise ValueError(f"在查询支付记录时传入的键值对参数 {', '.join(invalid_keys)} 无效。")

        query = self.db.collection("payments")
        for key in [
            "phone_number",
            "payment_id",
            "purchase_type",
            "sales_representative",
            "status",
            "is_approved",
        ]:
            if key in query_dict:
                query = query.where(filter=FieldFilter(key, "==", query_dict[key]))

        if "order_id" in query_dict:
            doc_ref = self.db.collection("payments").document(query_dict["order_id"])
            doc = doc_ref.get()
            if doc.exists:
                return [doc]
            else:
                return []

        for key in [
            "start_payment_time",
            "end_payment_time",
            "start_expiry_time",
            "end_expiry_time",
        ]:
            if key in query_dict:
                if "start" in key:
                    query = query.where(
                        filter=FieldFilter(
                            key.replace("start_", ""), ">=", query_dict[key]
                        )
                    )
                else:
                    query = query.where(
                        filter=FieldFilter(
                            key.replace("end_", ""), "<=", query_dict[key]
                        )
                    )
        results = query.stream()
        if "remark" in query_dict:
            results = [
                doc
                for doc in results
                if query_dict["remark"] in doc.to_dict().get("remark", "")
            ]
        if "payment_method" in query_dict:
            results = [
                doc
                for doc in results
                if query_dict["payment_method"]
                in doc.to_dict().get("payment_method", "")
            ]
        return results

    def update_payment(self, order_id, update_fields: dict):
        payments_ref = self.db.collection("payments")
        payment_doc_ref = payments_ref.document(order_id)
        payment_doc_ref.update(update_fields)

    def delete_payment(self, order_id):
        payments_ref = self.db.collection("payments")
        payment_doc_ref = payments_ref.document(order_id)
        payment_doc_ref.delete()

    def is_service_active(self, user_info: dict):
        if len(user_info) == 0:
            return False
        # 查询用户
        user_ref = self.db.collection("users").document(user_info["phone_number"])
        user = user_ref.get()
        # 如果用户是管理员，直接返回True
        if user.exists and user.to_dict()["user_role"] == "管理员":
            return True
        # 查询用户的所有支付记录
        payments = (
            self.db.collection("payments")
            .where(filter=FieldFilter("phone_number", "==", user_info["phone_number"]))
            .stream()
        )
        # 遍历所有支付记录
        now = datetime.now(timezone.utc)
        for payment in payments:
            payment_dict = payment.to_dict()
            # 如果找到一条已经被批准且服务尚未到期的记录，返回True
            expiry_time = payment_dict["expiry_time"].replace(tzinfo=timezone.utc)
            if payment_dict["is_approved"] and expiry_time > now:
                return True
        # 如果没有找到符合条件的记录，返回False
        return False

    def enable_service(self, payment: Payment):
        # 查询用户的最后一个订阅记录
        payments_ref = self.db.collection("payments")
        payments_query = (
            payments_ref.where(
                filter=FieldFilter("phone_number", "==", payment.phone_number)
            )
            .where(filter=FieldFilter("status", "==", PaymentStatus.IN_SERVICE))
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
            # 将字符串转换为 datetime 对象
            last_subscription_expiry_time = last_subscription["expiry_time"].replace(
                tzinfo=timezone.utc
            )
            if last_subscription_expiry_time > now:
                base_time = last_subscription_expiry_time

        # 将字符串转换为 PurchaseType 枚举
        expiry_time = base_time + self.calculate_expiry(payment.purchase_type)  # type: ignore

        # 更新支付记录对象的状态和到期时间
        payment.is_approved = True
        payment.expiry_time = expiry_time
        payment.status = PaymentStatus.IN_SERVICE

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
        user_doc_ref = users_ref.document(phone_number)
        user_doc = user_doc_ref.get()

        if not user_doc.exists:
            # 如果用户不存在，则创建一个新用户
            new_user = User(
                username=self.faker.user_name(),
                email=f"{phone_number}@{FAKE_EMAIL_DOMAIN}",
                password=phone_number,
                registration_time=datetime.now(timezone.utc),
                memo=f"订单号：{payment.order_id}",
            )  # type: ignore
            self.register_user(new_user)

        if payment.is_approved or (payment.receivable == payment.payment_amount):
            # 更新到期时间
            self.enable_service(payment)
        # 添加支付记录
        payments_ref = self.db.collection("payments")
        payment_data = payment.model_dump()
        # 从数据中删除 order_id
        del payment_data["order_id"]
        payment_doc_ref = payments_ref.document(payment.order_id)
        payment_doc_ref.set(payment_data, merge=True)

    # endregion

    # region 会话管理

    def generate_verification_code(self, phone_number: str):
        # 生成一个6位数的验证码
        verification_code = "".join(random.choice(string.digits) for _ in range(6))
        # 获取用户文档的引用
        user_doc_ref = self.db.collection("users").document(phone_number)
        # 更新用户的文档，添加验证码和生成时间
        user_doc_ref.update(
            {
                "verification_code": verification_code,
                "verification_code_time": datetime.now(timezone.utc),
            }
        )
        return verification_code

    def login_with_verification_code(self, phone_number: str, verification_code: str):
        # 在缓存中查询是否已经正常登录
        if (
            phone_number in self.cache
            and self.cache[phone_number].get("status", "") == "success"
        ):
            return {"status": "warning", "message": "您已登录"}

        # 获取用户文档的引用
        user_doc_ref = self.db.collection("users").document(phone_number)
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            user_data["phone_number"] = phone_number  # 添加手机号码
            user = User.from_doc(user_data)
            # 检查验证码是否正确
            if user_data.get("verification_code") == verification_code:
                # 检查验证码是否在有效期内
                if user_data.get("verification_code_time") + timedelta(
                    minutes=30
                ) > datetime.now(timezone.utc):
                    # 如果验证码正确且在有效期内，将用户的登录状态存储到缓存中
                    self.cache_user(user)
                    session_id = self.create_login_event(phone_number)
                    return {
                        "display_name": user.display_name,
                        "session_id": session_id,
                        "status": "success",
                        "user_role": user.user_role,
                        "timezone": user.timezone,
                        "message": f"嗨！{user.display_name}，又见面了。",
                    }
                else:
                    return {
                        "status": "error",
                        "message": "验证码已过期",
                    }
            else:
                return {
                    "status": "error",
                    "message": "验证码错误",
                }
        else:
            return {
                "status": "error",
                "message": f"不存在与手机号码 {phone_number} 相关联的用户",
            }

    def get_active_sessions(self, phone_number: str):
        login_events_ref = self.db.collection("login_events")
        login_events_query = (
            login_events_ref.where(
                filter=FieldFilter("phone_number", "==", phone_number)
            )
            .where(filter=FieldFilter("logout_time", "==", None))
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
