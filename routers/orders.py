"""
订单路由
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from database import get_db
from models import Order, User
from schemas import OrderCreate, OrderUpdate, OrderResponse
from datetime import datetime
from services.notification import send_order_notification
from services.feieyun import print_order as feieyun_print, test_print
from .auth import get_current_admin, _optional_admin
from auth import require_permission


def _get_setting(db: Session, key: str, default: str = "") -> str:
    from models import SystemSetting
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return s.value if s else default

router = APIRouter()

# 状态流转规则：key=当前状态，value=允许的目标状态列表
VALID_STATUS_TRANSITIONS = {
    "pending":                    ["confirmed", "cancelled", "cancellation_requested"],
    "confirmed":                 ["in_progress", "preparing", "cancelled", "cancellation_requested"],
    "in_progress":                ["preparing", "shipped"],
    "preparing":                  ["shipped"],
    "shipped":                    ["delivered"],
    "delivered":                  [],
    "cancelled":                  [],
    "cancellation_requested":     ["cancelled", "confirmed"],  # 管理员拒绝取消 → 恢复 confirmed
}


def is_valid_status_transition(current: str, new: str) -> bool:
    """检查状态流转是否合法"""
    if current == new:
        return True
    allowed = VALID_STATUS_TRANSITIONS.get(current, [])
    return new in allowed


def generate_order_no():
    return f"FX{datetime.now().strftime('%Y%m%d')}{datetime.now().strftime('%H%M%S')}"


def order_to_response(order: Order, user: User = None) -> dict:
    """将订单转换为响应格式，包含用户通知信息"""
    data = OrderResponse.model_validate(order).model_dump()
    if user:
        data["user_email"] = user.email
    return data


@router.get("")
def get_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Order)

    if status:
        query = query.filter(Order.status == status)

    if search:
        query = query.filter(
            (Order.order_no.contains(search)) |
            (Order.user_name.contains(search)) |
            (Order.phone.contains(search))
        )

    total = query.count()
    orders = query.order_by(desc(Order.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    # 获取用户信息
    items = []
    for order in orders:
        user = None
        if order.user_id:
            user = db.query(User).filter(User.id == order.user_id).first()
        items.append(order_to_response(order, user))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    user = None
    if order.user_id:
        user = db.query(User).filter(User.id == order.user_id).first()

    return order_to_response(order, user)


@router.post("")
def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    """创建订单"""
    user = None
    user_email = None

    # 如果有用户 token（非管理员），获取用户信息
    if authorization and authorization.startswith("Bearer "):
        from auth import decode_token
        token = authorization.replace("Bearer ", "")
        payload = decode_token(token)
        if payload and payload.get("type") == "user" and payload.get("role") != "admin":
            user_id_str = payload.get("sub")
            if user_id_str and user_id_str.isdigit():
                user_id = int(user_id_str)
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user_email = user.email

    # ========== 服务端计算订单金额（禁止客户端控制） ==========
    # 1. 计算商品小计
    subtotal = 0.0
    for item in order_data.items:
        price = float(item.get('price', 0))
        qty = int(item.get('quantity', 0))
        if price < 0 or qty < 1:
            raise HTTPException(status_code=400, detail="商品价格或数量无效")
        subtotal += price * qty

    # 2. 计算优惠券折扣
    discount_amount = 0.0
    coupon_code_used = None
    if order_data.coupon_code:
        from routers.coupons import _compute_coupon_discount
        try:
            discount_amount, coupon_code_used = _compute_coupon_discount(
                order_data.coupon_code, subtotal, user.id if user else None, db
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="优惠券无效")

    # 3. 最终金额
    final_total = max(0.0, subtotal - discount_amount)

    order = Order(
        order_no=generate_order_no(),
        user_id=user.id if user else order_data.user_id,
        user_name=order_data.user_name,
        total=round(final_total, 2),
        status=order_data.status,
        items=order_data.items,
        address=order_data.address,
        phone=order_data.phone,
        note=order_data.note,
        coupon_code=coupon_code_used,
        discount=round(discount_amount, 2),
        time_slot=order_data.time_slot,
        pay_method=order_data.pay_method
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # 管理员操作记录日志
    current_admin = _optional_admin(authorization)
    if current_admin:
        from .admin_logs import log_admin_action
        log_admin_action(
            db,
            admin_id=current_admin.get("id", 0),
            admin_name=current_admin.get("username", "admin"),
            action="create",
            target_type="order",
            target_id=order.id,
            detail=json.dumps({"key": "log_order_create", "order_no": order.order_no, "total": order.total})
        )

    # 更新用户积分和等级
    if user and final_total > 0:
        # 每消费 1 ฿ = 1 积分
        points_earned = int(final_total)
        user.points += points_earned
        user.total_spent += final_total

        # 检查是否升级
        new_level = calculate_level(user.total_spent)
        if new_level != user.level:
            user.level = new_level

        db.commit()

    # 发送订单确认通知（发给管理员）
    order_response = order_to_response(order, user)
    try:
        send_order_notification(db, order_response, "zh")
    except Exception:
        pass

    # 自动打印（如果开启）
    _auto_print(db, order_response)

    return order_response


@router.patch("/{order_id}")
def update_order(
    order_id: int,
    update_data: OrderUpdate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    """更新订单状态"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    old_status = order.status

    if update_data.status:
        # 校验状态流转是否合法
        if not is_valid_status_transition(old_status, update_data.status):
            raise HTTPException(
                status_code=400,
                detail=f"不允许从「{old_status}」修改为「{update_data.status}」"
            )
        order.status = update_data.status
        # 取消订单时记录时间
        if update_data.status == "cancelled":
            order.cancelled_at = datetime.now()
    if update_data.note is not None:
        order.note = update_data.note
    if update_data.shipped_image is not None:
        order.shipped_image = update_data.shipped_image
    if update_data.shipped_link is not None:
        order.shipped_link = update_data.shipped_link
    if update_data.delivered_image is not None:
        order.delivered_image = update_data.delivered_image
    # 退款相关
    if update_data.cancel_reason is not None:
        order.cancel_reason = update_data.cancel_reason
    if update_data.refund_amount is not None:
        order.refund_amount = update_data.refund_amount
    if update_data.refund_status is not None:
        order.refund_status = update_data.refund_status
        if update_data.refund_status == "approved":
            order.refunded_at = datetime.now()

    db.commit()
    db.refresh(order)

    # 记录日志
    from .admin_logs import log_admin_action
    log_admin_action(
        db,
        admin_id=current_admin["id"],
        admin_name=current_admin.get("username", "admin"),
        action="update",
        target_type="order",
        target_id=order_id,
        detail=json.dumps({"key": "log_order_update", "order_no": order.order_no, "old_status": old_status, "new_status": order.status})
    )

    # 获取用户信息用于发送通知
    user = None
    if order.user_id:
        user = db.query(User).filter(User.id == order.user_id).first()

    # 如果状态发生变化，发送通知（发给管理员）
    if old_status != order.status:
        order_response = order_to_response(order, user)
        try:
            send_order_notification(db, order_response, "zh")
        except Exception:
            pass

    # 始终返回订单响应
    order_response = order_to_response(order, user)
    return order_response


@router.delete("/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db),
                 current_admin: dict = Depends(require_permission("orders", "delete"))):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    db.delete(order)
    db.commit()

    # 记录日志
    from .admin_logs import log_admin_action
    log_admin_action(
        db,
        admin_id=0,
        admin_name="system",
        action="delete",
        target_type="order",
        target_id=order_id,
        detail=json.dumps({"key": "log_order_delete", "order_id": order_id})
    )

    return {"message": "订单已删除"}


def calculate_level(total_spent: float) -> str:
    """根据累计消费计算会员等级"""
    if total_spent >= 50000:
        return "diamond"
    elif total_spent >= 20000:
        return "gold"
    elif total_spent >= 5000:
        return "silver"
    return "normal"


def _auto_print(db: Session, order: dict):
    """检查配置，新订单自动打印"""
    auto_print = _get_setting(db, "feieyun_auto_print", "false")
    if auto_print != "true":
        return
    user = _get_setting(db, "feieyun_user")
    ukey = _get_setting(db, "feieyun_ukey")
    sn = _get_setting(db, "feieyun_sn")
    if not user or not ukey or not sn:
        return
    try:
        items = order.get("items", [])
        feieyun_print(user, ukey, sn, order, items, times=1, lang="th")
    except Exception:
        pass


@router.post("/{order_id}/print")
def print_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    """手动打印订单小票（飞鹅云打印机）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    user = _get_setting(db, "feieyun_user")
    ukey = _get_setting(db, "feieyun_ukey")
    sn = _get_setting(db, "feieyun_sn")
    if not user or not ukey or not sn:
        return {"success": False, "msg": "打印机未配置"}

    order_dict = order_to_response(order)
    items = order_dict.get("items", [])
    result = feieyun_print(user, ukey, sn, order_dict, items, times=1, lang="th")

    # 记录日志
    from .admin_logs import log_admin_action
    log_admin_action(
        db,
        admin_id=current_admin["id"],
        admin_name=current_admin.get("username", "admin"),
        action="print",
        target_type="order",
        target_id=order_id,
        detail=json.dumps({"key": "log_order_print", "order_no": order.order_no})
    )

    return result
