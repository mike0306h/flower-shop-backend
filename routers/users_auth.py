"""
用户认证路由 - 注册、登录、JWT
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
import bcrypt
from datetime import datetime
from database import get_db
from models import User, Order, EmailVerification
from schemas import UserRegister, UserLogin, UserUpdate, UserResponse, AuthResponse, ChangePassword, OrderResponse
from auth import create_token, get_current_user_optional
from services.notification import send_welcome_email

router = APIRouter()


def user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        name=user.name,
        level=user.level,
        points=user.points,
        total_spent=user.total_spent,
        email_notifications=user.email_notifications,
        avatar=user.avatar,
        created_at=user.created_at
    )


@router.post("/register", response_model=AuthResponse)
def register(data: UserRegister, db: Session = Depends(get_db)):
    """用户注册（需邮箱已验证）"""
    # 检查邮箱是否已存在
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    # 检查手机号是否已存在
    existing_phone = db.query(User).filter(User.phone == data.phone).first()
    if existing_phone:
        raise HTTPException(status_code=400, detail="该手机号已注册")

    # 检查邮箱是否已验证
    verified = db.query(EmailVerification).filter(
        EmailVerification.email == data.email,
        EmailVerification.type == "register",
        EmailVerification.used == True,
        EmailVerification.expires_at > datetime.utcnow()
    ).first()

    if not verified:
        raise HTTPException(status_code=403, detail="请先验证邮箱")

    # 创建用户
    user = User(
        email=data.email,
        phone=data.phone,
        name=data.name,
        password_hash=bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        level="normal",
        points=0,
        total_spent=0,
        source="email_register"
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 发送欢迎邮件（异步，不阻塞响应）
    try:
        send_welcome_email(user.email, user.name)
    except Exception:
        pass

    # 生成 Token
    token = create_token({
        "sub": str(user.id),
        "email": user.email,
        "type": "user"
    })

    return AuthResponse(
        token=token,
        user=user_to_response(user)
    )


@router.post("/login", response_model=AuthResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not bcrypt.checkpw(data.password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_token({
        "sub": str(user.id),
        "email": user.email,
        "type": "user"
    })

    return AuthResponse(
        token=token,
        user=user_to_response(user)
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user_optional)):
    """获取当前用户信息"""
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    user = db.query(User).filter(User.id == int(current_user["sub"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return user_to_response(user)


@router.put("/me", response_model=UserResponse)
def update_user(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional)
):
    """更新用户信息"""
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    user = db.query(User).filter(User.id == int(current_user["sub"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 更新字段
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user_to_response(user)


@router.get("/points")
def get_points(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional)
):
    """获取用户积分和等级"""
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    user = db.query(User).filter(User.id == int(current_user["sub"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {
        "points": user.points,
        "level": user.level,
        "total_spent": user.total_spent,
        "next_level": get_next_level(user.total_spent),
        "progress": get_level_progress(user.total_spent)
    }


def get_next_level(total_spent: float) -> dict:
    """计算下一个等级"""
    levels = [
        ("silver", 5000, "银卡会员", "🪙"),
        ("gold", 20000, "金卡会员", "🥇"),
        ("diamond", 50000, "钻卡会员", "💎")
    ]
    for level, threshold, name, icon in levels:
        if total_spent < threshold:
            return {"level": level, "name": name, "icon": icon, "threshold": threshold}
    return None


def get_level_progress(total_spent: float) -> float:
    """计算等级进度百分比"""
    levels = [("silver", 5000), ("gold", 20000), ("diamond", 50000)]
    for level, threshold in levels:
        if total_spent < threshold:
            return min(100, (total_spent / threshold) * 100)
    return 100


@router.post("/change-password")
def change_password(
    data: ChangePassword,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional)
):
    """修改密码"""
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    user = db.query(User).filter(User.id == int(current_user["sub"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 验证旧密码
    if not bcrypt.checkpw(data.old_password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=400, detail="原密码错误")

    # 更新新密码
    user.password_hash = bcrypt.hashpw(data.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.commit()

    return {"success": True, "message": "密码修改成功"}


@router.get("/orders")
def get_user_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional)
):
    """获取当前用户的订单历史"""
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    user_id = int(current_user["sub"])

    query = db.query(Order).filter(Order.user_id == user_id)
    total = query.count()
    orders = query.order_by(desc(Order.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [OrderResponse.model_validate(o).model_dump() for o in orders],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


# 用户取消订单申请
class CancelRequest(BaseModel):
    order_id: int
    reason: str


@router.post("/cancel-order")
def cancel_order_request(
    request: CancelRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional)
):
    """用户提交取消订单申请"""
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    user_id = int(current_user["sub"])

    # 检查订单是否存在且属于当前用户
    order = db.query(Order).filter(
        Order.id == request.order_id,
        Order.user_id == user_id
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 检查订单状态是否允许取消
    if order.status in ["cancelled", "delivered", "shipped"]:
        raise HTTPException(status_code=400, detail=f"当前状态「{order.status}」不允许取消")

    # 将取消原因存入 note 字段，状态改为 cancellation_requested
    order.note = (order.note or "") + f"\n[取消申请] {request.reason}"
    order.cancel_reason = request.reason
    order.status = "cancellation_requested"

    db.commit()
    db.refresh(order)

    # 发送通知给管理员
    from schemas import OrderResponse
    from services.notification import send_order_notification
    try:
        order_response = OrderResponse.model_validate(order).model_dump()
        send_order_notification(db, order_response, "zh")
    except Exception:
        pass

    return {"success": True, "message": "取消申请已提交，等待商家处理"}
