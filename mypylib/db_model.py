from datetime import datetime, timezone
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
    phone_number: str = Field(max_length=15)
    email: str = Field("")
    full_name: str = Field("")
    display_name: str = Field("", max_length=100)
    password: str = Field("", min_length=8)
    country: str = Field("")  # 新增国家字段
    province: str = Field("")
    timezone: str = Field("")  # 新增时区字段
    permission: UserRole = Field(default=UserRole.USER)
    registration_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )  # 新增注册时间字段
    session_id: str = Field("")  # 新增会话ID字段
    login_events: List[LoginEvent] = Field(default_factory=list)
    memo: str = Field("")  # 新增备注字段

    def hash_password(self):
        self.password = generate_password_hash(self.password)

    def check_password(self, password):
        return check_password_hash(self.password, password)
