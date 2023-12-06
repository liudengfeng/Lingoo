# models.py
from datetime import datetime
from enum import Enum
from typing import List, Optional, Type, Union

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


class EventType(Enum):
    LOGIN = "login"
    LOGOUT = "logout"


class LoginEvent(BaseModel):
    type: EventType
    time: datetime


def str_to_enum(s: str, enum_type: Type[Enum]) -> Union[Enum, str]:
    for t in enum_type:
        if t.value == s:
            return t
    return None  # type: ignore


class Payment(BaseModel):
    phone_number: str = Field(max_length=15)
    payment_id: str
    order_id: str
    payment_time: datetime = Field(default_factory=datetime.utcnow)
    receivable: float = Field(gt=0.0, le=100000.0)
    discount_rate: float = Field(0.0, ge=0.0)  # 新增折扣率字段
    payment_amount: float = Field(ge=0.0, le=100000.0)
    purchase_type: PurchaseType = Field(default=PurchaseType.DAILY)
    payment_method: str = Field("")  # 新增支付方式字段
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)
    is_approved: bool = Field(False)
    expiry_time: datetime = Field(default_factory=datetime.utcnow)
    remark: str = Field("")  # 新增备注字段


class User(BaseModel):
    phone_number: str = Field(max_length=15)
    email: str = Field("")
    name: str = Field("")
    username: str = Field("", max_length=20)
    password: str = Field("", min_length=8)
    country: str = Field("")  # 新增国家字段
    province: str = Field("")
    timezone: str = Field("")  # 新增时区字段
    permission: UserRole = Field(default=UserRole.USER)
    registration_time: datetime = Field(default_factory=datetime.utcnow)  # 新增注册时间字段
    memo: str = Field("")  # 新增备注字段
    session_id: str = Field("")  # 新增会话ID字段
    login_events: List[LoginEvent] = Field(default_factory=list)

    def hash_password(self):
        self.password = generate_password_hash(self.password)

    def check_password(self, password):
        return check_password_hash(self.password, password)
