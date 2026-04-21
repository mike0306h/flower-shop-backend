"""
数据模型
"""
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    # 角色: super_admin / admin / staff / viewer
    role = Column(String(20), default="staff")
    # 姓名
    name = Column(String(100))
    # 手机号
    phone = Column(String(20))
    # 部门
    department = Column(String(50))
    # 是否启用
    is_active = Column(Boolean, default=True)
    # 创建人
    created_by = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    # 最后登录时间
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True)
    phone = Column(String(20), unique=True, index=True)
    name = Column(String(100))
    password_hash = Column(String(255))
    # 状态: active / banned / suspended
    status = Column(String(20), default="active", index=True)
    # 会员等级: normal / silver / gold / diamond
    level = Column(String(20), default="normal", index=True)
    # 会员积分
    points = Column(Integer, default=0)
    # 累计消费金额
    total_spent = Column(Float, default=0)
    # 用户来源: wechat / line / phone / manual
    source = Column(String(20), default="manual")
    # Line Token for notifications
    line_token = Column(String(255), nullable=True)
    # 最后登录时间
    last_login = Column(DateTime, nullable=True)
    # 通知设置
    email_notifications = Column(Boolean, default=True)
    # 头像
    avatar = Column(String(255), default="👤")
    created_at = Column(DateTime, server_default=func.now())

    addresses = relationship("Address", back_populates="user")


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(100))
    phone = Column(String(20))
    full_address = Column(Text)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="addresses")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    name_th = Column(String(200))
    name_en = Column(String(200))
    description = Column(Text)
    description_th = Column(Text)
    description_en = Column(Text)
    price = Column(Float, nullable=False)
    original_price = Column(Float)
    images = Column(JSON, default=list)  # ["url1", "url2"]
    stock = Column(Integer, default=0)
    stock_threshold = Column(Integer, default=10)  # 库存预警阈值
    notify_low_stock = Column(Boolean, default=True)  # 是否启用预警
    category = Column(String(50), index=True)
    tags = Column(JSON, default=list)  # ["热卖", "新品"]
    # 花朵规格选项： [{"count": 11, "price": 299}, {"count": 52, "price": 999}]
    flower_options = Column(JSON, default=list)
    language = Column(String(10), default="all")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_name = Column(String(100))
    total = Column(Float, nullable=False)
    status = Column(String(20), default="pending", index=True)
    items = Column(JSON, default=list)  # [{"productId": 1, "name": "...", "price": 299, "quantity": 1, "flowers": 11}]
    address = Column(Text)
    phone = Column(String(20))
    note = Column(Text)
    coupon_code = Column(String(50))
    discount = Column(Float, default=0)
    time_slot = Column(String(20))
    pay_method = Column(String(20))
    shipped_image = Column(Text)
    shipped_link = Column(Text)
    delivered_image = Column(Text)
    # 取消/退款
    cancel_reason = Column(Text)
    refund_amount = Column(Float, default=0)
    refund_status = Column(String(20), default="none")  # none/requested/approved/rejected
    cancelled_at = Column(DateTime)
    refunded_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    appointment_no = Column(String(50), unique=True, index=True, nullable=False)
    customer_name = Column(String(100))
    customer_phone = Column(String(20))
    occasion = Column(String(50))
    budget = Column(String(50))
    delivery_date = Column(String(20))
    delivery_time = Column(String(20))
    recipient_name = Column(String(100))
    recipient_phone = Column(String(20))
    delivery_address = Column(Text)
    reference_images = Column(JSON, default=list)
    requirements = Column(Text)
    blessing_card = Column(String(200))
    packaging = Column(String(100))
    callback_time = Column(String(50))
    status = Column(String(20), default="pending", index=True)
    note = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    phone = Column(String(20))
    message = Column(Text)
    reply = Column(Text)
    status = Column(String(20), default="pending", index=True)
    created_at = Column(DateTime, server_default=func.now())


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    discount_type = Column(String(20), default="percent")  # percent / fixed
    discount_value = Column(Float, nullable=False)
    min_amount = Column(Float, default=0)  # 最低消费金额
    max_uses = Column(Integer, default=0)  # 0 = 无限制
    used_count = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Review(Base):
    """商品评价"""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    rating = Column(Integer, nullable=False)  # 1-5星
    comment = Column(Text)
    images = Column(JSON, default=list)  # 评价图片
    is_verified = Column(Boolean, default=False)  # 是否已购买验证
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AdminLog(Base):
    """管理员操作日志"""
    __tablename__ = "admin_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer)
    admin_name = Column(String(100))
    action = Column(String(50))  # create/update/delete
    target_type = Column(String(50))  # order/product/user/coupon
    target_id = Column(Integer)
    detail = Column(Text)  # 操作详情
    created_at = Column(DateTime, server_default=func.now())


class Category(Base):
    """商品分类（多语言 + 排序 + 图片）"""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(50), unique=True, index=True, nullable=False)  # e.g. "bouquet", "rose"
    name_zh = Column(String(100), nullable=False)  # 中文名
    name_th = Column(String(100), nullable=False)  # 泰文名
    name_en = Column(String(100), nullable=False)  # 英文名
    image = Column(String(500), nullable=True)  # 分类图片URL
    emoji = Column(String(10), default='🌸')   # 分类emoji图标
    sort_order = Column(Integer, default=0)  # 排序，数字越小越靠前
    active = Column(Boolean, default=True)
    show_on_home = Column(Boolean, default=True)  # 是否在首页/商城前台显示
    created_at = Column(DateTime, server_default=func.now())


class NotificationChannel(Base):
    """通知渠道（支持多个邮箱和LINE账号）"""
    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(20), nullable=False)  # 'email' or 'line'
    value = Column(String(255), nullable=False)  # 邮箱地址或LINE Notify Token
    name = Column(String(100))  # 渠道别名，如"店长手机"
    recipient_name = Column(String(100))  # 接收人姓名，如"店长 Sarah"
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class SystemSetting(Base):
    """系统配置（通知渠道凭证等）"""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(255))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopInfo(Base):
    """店铺信息（前台展示用：地址、电话、营业时间、Line二维码）"""
    __tablename__ = "shop_info"

    id = Column(Integer, primary_key=True, index=True)
    address_zh = Column(String(255), default='')
    address_th = Column(String(255), default='')
    address_en = Column(String(255), default='')
    phone = Column(String(50), default='')
    hours_zh = Column(String(255), default='')
    hours_th = Column(String(255), default='')
    hours_en = Column(String(255), default='')
    line_qr_image = Column(String(500), default='')  # Line QR码图片URL
    shop_name = Column(String(255), default='')  # 店铺名称
    logo_url = Column(String(500), default='')  # 店铺Logo URL
    email = Column(String(100), default='')  # 店铺邮箱
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class EmailVerification(Base):
    """邮箱验证码（注册验证 + 找回密码）"""
    __tablename__ = "email_verifications"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), nullable=False, index=True)
    code = Column(String(64), nullable=False)  # 6位验证码
    type = Column(String(20), nullable=False)  # 'register' / 'reset_password'
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
