"""
Pydantic 模型 - 请求/响应 schema
"""
import re
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from datetime import datetime


# ============ Auth ============
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict
    permissions: List[str] = []


# ============ AdminUser ============
class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = "staff"
    name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None


class AdminUserResponse(BaseModel):
    id: int
    username: str
    role: str
    name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminUserListResponse(BaseModel):
    total: int
    items: List[AdminUserResponse]


class UserInfo(BaseModel):
    id: int
    username: str
    role: str


# ============ 订单 ============
class OrderItem(BaseModel):
    productId: int
    name: str
    price: float
    quantity: int
    flowers: int


class OrderCreate(BaseModel):
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    # total 和 discount 由服务端计算，禁止客户端提交
    status: str = "pending"
    items: List[dict]
    address: str
    phone: str
    note: Optional[str] = None
    coupon_code: Optional[str] = None
    time_slot: Optional[str] = None
    pay_method: Optional[str] = None

    @field_validator('items')
    @classmethod
    def items_not_empty(cls, v):
        if not v:
            raise ValueError('订单商品不能为空')
        for item in v:
            if item.get('quantity', 0) < 1:
                raise ValueError('商品数量必须 >= 1')
            if item.get('price', 0) < 0:
                raise ValueError('商品价格不能为负数')
        return v

    @field_validator('phone')
    @classmethod
    def phone_not_empty(cls, v):
        if not v or len(str(v).strip()) < 8:
            raise ValueError('手机号格式不正确')
        return v.strip()


class OrderUpdate(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None
    shipped_image: Optional[str] = None
    shipped_link: Optional[str] = None
    delivered_image: Optional[str] = None
    cancel_reason: Optional[str] = None
    refund_amount: Optional[float] = None
    refund_status: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    order_no: str
    user_id: Optional[int]
    user_name: Optional[str]
    total: float
    status: str
    items: List[dict]
    address: str
    phone: str
    note: Optional[str]
    coupon_code: Optional[str]
    discount: float = 0
    time_slot: Optional[str] = None
    pay_method: Optional[str] = None
    shipped_image: Optional[str] = None
    shipped_link: Optional[str] = None
    delivered_image: Optional[str] = None
    cancel_reason: Optional[str] = None
    refund_amount: float = 0
    refund_status: str = "none"
    cancelled_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 预约 ============


# ============ 商品 ============
class ProductCreate(BaseModel):
    name: str
    name_th: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    description_th: Optional[str] = None
    description_en: Optional[str] = None
    price: float
    original_price: Optional[float] = None
    images: Optional[List[str]] = None
    stock: int = 0
    stock_threshold: int = 10
    notify_low_stock: bool = True
    category: str = "bouquet"
    tags: Optional[List[str]] = None
    flower_options: Optional[List[dict]] = None  # [{"count": 11, "price": 299}, {"count": 52, "price": 999}]
    language: str = "all"
    active: bool = True

    @field_validator('flower_options', 'images', 'tags', mode='before')
    @classmethod
    def empty_list(cls, v):
        if v is None:
            return []
        return v

    @field_validator('price')
    @classmethod
    def price_positive(cls, v):
        if v is None:
            return None
        if v < 0:
            raise ValueError('商品价格不能为负数')
        return v

    @field_validator('stock')
    @classmethod
    def stock_non_negative(cls, v):
        if v is None:
            return None
        if v < 0:
            raise ValueError('库存不能为负数')
        return v


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    name_th: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    description_th: Optional[str] = None
    description_en: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    images: Optional[List[str]] = None
    stock: Optional[int] = None
    stock_threshold: Optional[int] = None
    notify_low_stock: Optional[bool] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    flower_options: Optional[List[dict]] = None
    language: Optional[str] = None
    active: Optional[bool] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    name_th: Optional[str]
    name_en: Optional[str]
    description: Optional[str]
    price: float
    original_price: Optional[float]
    images: Optional[List[str]]
    stock: int
    stock_threshold: Optional[int] = None
    notify_low_stock: Optional[bool] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    flower_options: Optional[List[dict]] = None
    language: Optional[str] = None
    active: Optional[bool] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator('flower_options', 'images', 'tags', mode='before')
    @classmethod
    def empty_list(cls, v):
        if v is None:
            return []
        return v


# ============ 用户 ============
class UserRegister(BaseModel):
    name: str
    email: str
    phone: str
    password: str

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('密码长度至少8位')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('密码必须包含字母')
        if not re.search(r'\d', v):
            raise ValueError('密码必须包含数字')
        return v


class UserLogin(BaseModel):
    email: str
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email_notifications: Optional[bool] = None
    avatar: Optional[str] = None


class ChangePassword(BaseModel):
    old_password: str
    new_password: str


class UserResponse(BaseModel):
    id: int
    email: Optional[str]
    phone: Optional[str]
    name: Optional[str]
    status: str = "active"
    level: str = "normal"
    points: Optional[int] = None
    total_spent: Optional[float] = None
    source: Optional[str] = None
    last_login: Optional[datetime] = None
    email_notifications: Optional[bool] = None
    avatar: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdateByAdmin(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    level: Optional[str] = None
    points: Optional[int] = None
    status: Optional[str] = None
    source: Optional[str] = None
    email_notifications: Optional[bool] = None


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


# ============ 预约 ============
class AppointmentCreate(BaseModel):
    customer_name: str
    customer_phone: str
    occasion: str
    budget: str
    delivery_date: Optional[str] = None
    delivery_time: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None
    delivery_address: Optional[str] = None
    reference_images: Optional[List[str]] = []
    requirements: Optional[str] = None
    blessing_card: Optional[str] = None
    packaging: Optional[str] = None
    callback_time: Optional[str] = None


class AppointmentUpdate(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None
    packaging: Optional[str] = None
    callback_time: Optional[str] = None
    reference_images: Optional[List[str]] = None


class AppointmentResponse(BaseModel):
    id: int
    appointment_no: str
    customer_name: str
    customer_phone: str
    occasion: str
    budget: str
    delivery_date: Optional[str]
    delivery_time: Optional[str]
    recipient_name: Optional[str]
    recipient_phone: Optional[str]
    delivery_address: Optional[str]
    reference_images: Optional[List[str]] = []
    requirements: Optional[str]
    blessing_card: Optional[str]
    packaging: Optional[str]
    callback_time: Optional[str]
    status: str
    note: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 联系 ============
class ContactCreate(BaseModel):
    name: str
    phone: str
    message: str


class ContactUpdate(BaseModel):
    status: Optional[str] = None
    reply: Optional[str] = None


class ContactResponse(BaseModel):
    id: int
    name: str
    phone: str
    message: str
    status: str
    reply: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 统计 ============
class StatsResponse(BaseModel):
    todayOrders: int
    todaySales: float
    totalOrders: int
    totalSales: float
    totalProducts: int
    totalUsers: int
    pendingOrders: int
    pendingAppointments: int
    pendingContacts: int


# ============ 优惠券 ============
class CouponCreate(BaseModel):
    code: str
    discount_type: str = "percent"
    discount_value: float
    min_amount: float = 0
    max_uses: int = 0
    expires_at: Optional[str] = None


class CouponUpdate(BaseModel):
    code: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    min_amount: Optional[float] = None
    max_uses: Optional[int] = None
    active: Optional[bool] = None
    expires_at: Optional[str] = None


class CouponResponse(BaseModel):
    id: int
    code: str
    discount_type: str
    discount_value: float
    min_amount: float
    max_uses: int
    used_count: int
    active: bool
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 配送员 ============
class DeliveryPersonCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    avatar: Optional[str] = None
    status: str = "available"


class DeliveryPersonUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    status: Optional[str] = None


class DeliveryPersonResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    avatar: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 商品评价 ============
class ReviewCreate(BaseModel):
    product_id: int
    rating: int  # 1-5
    comment: Optional[str] = None
    images: Optional[List[str]] = []


class ReviewUpdate(BaseModel):
    rating: Optional[int] = None
    comment: Optional[str] = None
    images: Optional[List[str]] = None
    active: Optional[bool] = None


class ReviewResponse(BaseModel):
    id: int
    product_id: int
    user_id: int
    order_id: Optional[int]
    rating: int
    comment: Optional[str]
    images: List[str]
    is_verified: bool
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 操作日志 ============
class AdminLogResponse(BaseModel):
    id: int
    admin_id: Optional[int]
    admin_name: Optional[str]
    action: str
    target_type: str
    target_id: Optional[int]
    detail: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 分类 ============
class CategoryCreate(BaseModel):
    slug: str
    name_zh: str
    name_th: str
    name_en: str
    image: Optional[str] = None  # 分类图片URL
    emoji: Optional[str] = '🌸'  # 分类emoji
    sort_order: int = 0
    active: bool = True
    show_on_home: bool = True  # 是否在首页/商城前台显示


class CategoryUpdate(BaseModel):
    slug: Optional[str] = None
    name_zh: Optional[str] = None
    name_th: Optional[str] = None
    name_en: Optional[str] = None
    image: Optional[str] = None
    emoji: Optional[str] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None
    show_on_home: Optional[bool] = None


class CategoryResponse(BaseModel):
    id: int
    slug: str
    name_zh: str
    name_th: Optional[str] = None
    name_en: Optional[str] = None
    image: Optional[str] = None
    emoji: Optional[str] = '🌸'
    sort_order: Optional[int] = 0
    active: Optional[bool] = True
    show_on_home: Optional[bool] = True
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 通知渠道 ============
class NotificationChannelCreate(BaseModel):
    type: str  # 'email' or 'line'
    value: str  # 邮箱地址或LINE Notify Token
    name: Optional[str] = None  # 渠道别名
    recipient_name: Optional[str] = None  # 接收人姓名


class NotificationChannelUpdate(BaseModel):
    type: Optional[str] = None
    value: Optional[str] = None
    name: Optional[str] = None
    recipient_name: Optional[str] = None
    enabled: Optional[bool] = None


class NotificationChannelResponse(BaseModel):
    id: int
    type: str
    value: str  # 邮箱时返回脱敏值
    name: Optional[str]
    recipient_name: Optional[str]
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 店铺信息 ============
class ShopInfoUpdate(BaseModel):
    address_zh: Optional[str] = None
    address_th: Optional[str] = None
    address_en: Optional[str] = None
    phone: Optional[str] = None
    hours_zh: Optional[str] = None
    hours_th: Optional[str] = None
    hours_en: Optional[str] = None
    line_qr_image: Optional[str] = None
    email: Optional[str] = None
    shop_name: Optional[str] = None
    logo_url: Optional[str] = None
    seo_keywords: Optional[str] = None
    seo_description: Optional[str] = None


class ShopInfoResponse(BaseModel):
    id: int
    address_zh: str
    address_th: str
    address_en: str
    phone: str
    hours_zh: str
    hours_th: str
    hours_en: str
    line_qr_image: str
    email: str
    shop_name: str
    logo_url: str
    seo_keywords: str
    seo_description: str
    updated_at: datetime

    class Config:
        from_attributes = True


class SystemSettingItem(BaseModel):
    id: int
    key: str
    value: Optional[str]
    description: Optional[str]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class SMTPSettingUpdate(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[str] = None

# ============ 用户地址 ============
class AddressCreate(BaseModel):
    user_id: int
    name: str
    phone: str
    full_address: str
    is_default: bool = False


class AddressUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    full_address: Optional[str] = None
    is_default: Optional[bool] = None


class AddressResponse(BaseModel):
    id: int
    user_id: int
    name: str
    phone: str
    full_address: str
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 邮箱验证 ============
class SendVerifyEmailRequest(BaseModel):
    email: str


class SendResetPasswordEmailRequest(BaseModel):
    email: str


class VerifyEmailRequest(BaseModel):
    code: str


class ResetPasswordRequest(BaseModel):
    code: str
    new_password: str


class VerifyEmailResponse(BaseModel):
    success: bool
    message: str
    user: Optional[dict] = None
    token: Optional[str] = None
    # register 时 email_verification 已标记 used，但 user 还不存在
    # 所以这里只返回成功，前端再调用 /register 完成注册并登录


class SendEmailResponse(BaseModel):
    success: bool
    message: str
