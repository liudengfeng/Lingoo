from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Type, Union
from bson import ObjectId

from cryptography.fernet import Fernet
from pydantic import BaseModel, Field
from werkzeug.security import check_password_hash, generate_password_hash


class PurchaseType(str, Enum):
    ANNUAL = "年度"
    QUARTERLY = "季度"
    MONTHLY = "月度"
    WEEKLY = "每周"
    DAILY = "每日"


class UserRole(str, Enum):
    USER = "用户"
    VIP = "VIP"
    ADMIN = "管理员"


class PaymentStatus(str, Enum):
    PENDING = "待定"
    RETURNED = "返还"
    IN_SERVICE = "服务中"
    COMPLETED = "完成"


class LoginEvent(BaseModel):
    login_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    logout_time: Optional[datetime] = Field(default=None)
    session_id: str = Field("")


def str_to_enum(s: str, enum_type: Type[Enum]) -> Union[Enum, str]:
    for t in enum_type:
        if t.value == s:
            return t
    return None  # type: ignore


class Payment(BaseModel):
    phone_number: str = Field(max_length=15)
    payment_id: str
    order_id: str
    payment_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    receivable: float = Field(gt=0.0, le=100000.0)
    discount_rate: float = Field(0.0, ge=0.0)  # 新增折扣率字段
    payment_amount: float = Field(ge=0.0, le=100000.0)
    purchase_type: PurchaseType = Field(default=PurchaseType.DAILY)
    payment_method: str = Field("")  # 新增支付方式字段
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)
    is_approved: bool = Field(False)
    expiry_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    remark: str = Field("")  # 新增备注字段


class User(BaseModel):
    # 私有字段
    _secret_key: bytes
    _user_id: Optional[str]

    # 加密字段
    f_email: bytes = Field(b"")
    f_real_name: bytes = Field(b"")
    f_country: bytes = Field(b"")  # 新增国家字段
    f_province: bytes = Field(b"")
    f_timezone: bytes = Field(b"")  # 新增时区字段

    phone_number: str = Field("", max_length=15)
    display_name: str = Field("", max_length=100)
    current_level: str = Field("A1")
    target_level: str = Field("C1")
    password: str = Field("12345678")
    user_role: UserRole = Field(default=UserRole.USER)
    registration_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )  # 新增注册时间字段
    login_events: Optional[List[LoginEvent]] = Field(default_factory=list)
    memo: Optional[str] = Field("")  # 新增备注字段

    @classmethod
    def from_doc(cls, doc: dict):
        cls._user_id = str(doc.pop("_id", None))
        return cls(**doc)

    @classmethod
    def encrypt(cls, value: str, key: bytes) -> bytes:
        if isinstance(key, str):
            key = key.encode()
        cipher_suite = Fernet(key)
        encrypted_bytes = cipher_suite.encrypt(value.encode())
        return encrypted_bytes

    @classmethod
    def decrypt(cls, b_value: bytes, key: bytes) -> str:
        if isinstance(key, str):
            key = key.encode()
        cipher_suite = Fernet(key)
        decrypted_text = cipher_suite.decrypt(b_value)
        return decrypted_text.decode()

    @property
    def user_id(self):
        return self._user_id

    def set_secret_key(self, key: bytes):
        self._secret_key = key

    @property
    def _cipher_suite(self):
        if self._secret_key is None:
            raise ValueError("Key is not set.")
        return Fernet(self._secret_key)

    @property
    def phone_number(self):
        # 解密手机号码
        return self._cipher_suite.decrypt(self.f_phone_number).decode()

    @phone_number.setter
    def phone_number(self, value):
        # 加密手机号码
        self.f_phone_number = self._cipher_suite.encrypt(value.encode())

    @property
    def email(self):
        # 解密电子邮件地址
        return self._cipher_suite.decrypt(self._email).decode()

    @email.setter
    def email(self, value):
        # 加密电子邮件地址
        self.f_email = self._cipher_suite.encrypt(value.encode())

    @property
    def real_name(self):
        # 解密真实名字
        return self._cipher_suite.decrypt(self._real_name).decode()

    @real_name.setter
    def real_name(self, value):
        # 加密真实名字
        self.f_real_name = self._cipher_suite.encrypt(value.encode())

    @property
    def country(self):
        # 解密国家
        return self._cipher_suite.decrypt(self._country).decode()

    @country.setter
    def country(self, value):
        # 加密国家
        self.f_country = self._cipher_suite.encrypt(value.encode())

    @property
    def province(self):
        # 解密省份
        return self._cipher_suite.decrypt.decrypt(self._province).decode()

    @province.setter
    def province(self, value):
        # 加密省份
        self.f_province = self._cipher_suite.encrypt(value.encode())

    @property
    def timezone(self):
        # 解密时区
        return self._cipher_suite.decrypt(self._timezone).decode()

    @timezone.setter
    def timezone(self, value):
        # 加密时区
        self.f_timezone = self._cipher_suite.encrypt(value.encode())

    def hash_password(self):
        self.password = generate_password_hash(self.password)

    def check_password(self, password):
        return check_password_hash(self.password, password)
