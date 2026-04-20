"""
用户管理路由
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import Optional
from datetime import datetime
import bcrypt
from database import get_db
from models import User, Order, Address, Product
from schemas import UserResponse, UserUpdateByAdmin, AddressCreate, AddressUpdate, AddressResponse
from auth import get_current_admin

router = APIRouter()


@router.get("")
def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    level: Optional[str] = None,
    source: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """获取用户列表，支持多维度筛选"""
    query = db.query(User)

    # 模糊搜索
    if search:
        query = query.filter(
            (User.email.contains(search)) |
            (User.name.contains(search)) |
            (User.phone.contains(search))
        )

    # 状态筛选
    if status and status != 'all':
        query = query.filter(User.status == status)

    # 等级筛选
    if level and level != 'all':
        query = query.filter(User.level == level)

    # 来源筛选
    if source and source != 'all':
        query = query.filter(User.source == source)

    # 排序
    sort_column = getattr(User, sort_by, User.created_at)
    if sort_order == 'desc':
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)

    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()

    # 补充每个用户的订单统计
    user_ids = [u.id for u in users]
    order_counts = {}
    order_totals = {}
    if user_ids:
        stats = db.query(
            Order.user_id,
            func.count(Order.id).label('order_count'),
            func.coalesce(func.sum(Order.total), 0).label('order_total')
        ).filter(
            Order.user_id.in_(user_ids),
            Order.status.notin_(['cancelled'])
        ).group_by(Order.user_id).all()
        for s in stats:
            order_counts[s.user_id] = s.order_count
            order_totals[s.user_id] = float(s.order_total)

    items = []
    for u in users:
        data = UserResponse.model_validate(u).model_dump()
        data['order_count'] = order_counts.get(u.id, 0)
        data['order_total'] = order_totals.get(u.id, 0)
        items.append(data)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    """获取单个用户详情（含统计）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 订单统计
    order_stats = db.query(
        func.count(Order.id).label('total_orders'),
        func.coalesce(func.sum(Order.total), 0).label('total_spent'),
        func.coalesce(func.avg(Order.total), 0).label('avg_order')
    ).filter(Order.user_id == user_id, Order.status.notin_(['cancelled'])).first()

    # 最近5笔订单
    recent_orders = db.query(Order).filter(
        Order.user_id == user_id,
        Order.status.notin_(['cancelled'])
    ).order_by(desc(Order.created_at)).limit(5).all()

    resp = UserResponse.model_validate(user).model_dump()
    resp['order_count'] = order_stats.total_orders or 0
    resp['order_total'] = float(order_stats.total_spent) if order_stats.total_spent else 0
    resp['avg_order'] = float(order_stats.avg_order) if order_stats.avg_order else 0
    resp['recent_orders'] = [{
        'id': o.id,
        'status': o.status,
        'total': o.total,
        'created_at': o.created_at.isoformat() if o.created_at else None
    } for o in recent_orders]

    return resp


@router.get("/{user_id}/orders")
def get_user_orders(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """获取用户的全部订单"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    query = db.query(Order).filter(Order.user_id == user_id).order_by(desc(Order.created_at))
    total = query.count()
    orders = query.offset((page - 1) * page_size).limit(page_size).all()

    # 收集所有 product_id 并查询图片
    all_product_ids = set()
    for order in orders:
        for item in (order.items or []):
            if item.get('productId'):
                all_product_ids.add(item['productId'])
    product_images = {}
    if all_product_ids:
        products = db.query(Product).filter(Product.id.in_(all_product_ids)).all()
        for p in products:
            img_list = p.images if p.images else []
            product_images[p.id] = img_list[0] if img_list else None

    # 收集所有 user_id 并查询邮箱
    all_user_ids = set(o.user_id for o in orders if o.user_id)
    user_emails = {}
    if all_user_ids:
        user_rows = db.query(User.id, User.email).filter(User.id.in_(all_user_ids)).all()
        for u in user_rows:
            user_emails[u.id] = u.email

    # 组装返回数据，给每个 item 附上图片，给每个订单附上用户邮箱
    items = []
    for order in orders:
        order_data = {
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "user_name": order.user_name,
            "user_email": user_emails.get(order.user_id) if order.user_id else None,
            "total": order.total,
            "status": order.status,
            "address": order.address,
            "phone": order.phone,
            "note": order.note,
            "coupon_code": order.coupon_code,
            "discount": order.discount,
            "time_slot": order.time_slot,
            "pay_method": order.pay_method,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }
        # 给 items 附上产品图片
        enriched_items = []
        for item in (order.items or []):
            item_copy = dict(item)
            pid = item.get('productId')
            if pid and pid in product_images:
                item_copy['image'] = product_images[pid]
            else:
                item_copy['image'] = None
            enriched_items.append(item_copy)
        order_data['items'] = enriched_items
        items.append(order_data)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.get("/{user_id}/addresses")
def get_user_addresses(user_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    addresses = db.query(Address).filter(Address.user_id == user_id).all()
    return addresses


@router.put("/{user_id}")
def update_user(user_id: int, data: UserUpdateByAdmin, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    """管理员更新用户信息"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="update", target_type="user", target_id=user_id,            detail=json.dumps({"key": "log_user_update", "user_id": user_id}))

    return UserResponse.model_validate(user).model_dump()


@router.post("/{user_id}/points")
def adjust_points(user_id: int, points: int = Query(..., description="调整积分数（正数增加，负数减少）"), reason: str = Query("", description="调整原因"), db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    """增减用户积分"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    new_points = (user.points or 0) + points
    if new_points < 0:
        raise HTTPException(status_code=400, detail="积分不能为负数")

    user.points = new_points
    db.commit()
    db.refresh(user)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="adjust_points", target_type="user", target_id=user_id, detail=json.dumps({"key": "log_points_adjust", "user_id": user_id, "points": points, "reason": reason}))

    return {"user_id": user_id, "points": user.points, "adjustment": points}


@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, new_password: str = Query(..., min_length=6, description="新密码"), db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    """管理员重置用户密码"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.commit()

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="reset_password", target_type="user", target_id=user_id, detail=json.dumps({"key": "log_password_reset", "user_id": user_id}))

    return {"message": "密码重置成功", "user_id": user_id}


# ============ 地址管理 ============

@router.post("/addresses")
def create_address(data: AddressCreate, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    """创建收货地址"""
    # 如果设为默认，先取消其他默认
    if data.is_default:
        db.query(Address).filter(Address.user_id == data.user_id).update({"is_default": False})
    addr = Address(**data.model_dump())
    db.add(addr)
    db.commit()
    db.refresh(addr)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="create", target_type="address", target_id=addr.id, detail=json.dumps({"key": "log_address_create", "address_id": addr.id}))

    return AddressResponse.model_validate(addr).model_dump()


@router.put("/addresses/{address_id}")
def update_address(address_id: int, data: AddressUpdate, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    """更新收货地址"""
    addr = db.query(Address).filter(Address.id == address_id).first()
    if not addr:
        raise HTTPException(status_code=404, detail="地址不存在")

    # 如果设为默认，先取消其他默认
    if data.is_default:
        db.query(Address).filter(Address.user_id == addr.user_id, Address.id != address_id).update({"is_default": False})

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(addr, field, value)

    db.commit()
    db.refresh(addr)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="update", target_type="address", target_id=address_id, detail=json.dumps({"key": "log_address_update", "address_id": address_id}))

    return AddressResponse.model_validate(addr).model_dump()


@router.delete("/addresses/{address_id}")
def delete_address(address_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    """删除收货地址"""
    addr = db.query(Address).filter(Address.id == address_id).first()
    if not addr:
        raise HTTPException(status_code=404, detail="地址不存在")

    db.delete(addr)
    db.commit()

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="delete", target_type="address", target_id=address_id, detail=json.dumps({"key": "log_address_delete", "address_id": address_id}))

    return {"message": "删除成功"}
