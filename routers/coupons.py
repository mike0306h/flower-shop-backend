"""
优惠券管理
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
from models import Coupon
from schemas import CouponCreate, CouponUpdate, CouponResponse
from auth import get_current_admin, require_permission

router = APIRouter()


# 公开接口：获取可用优惠券列表（用户可见）
@router.get("/available", response_model=dict)
def get_available_coupons(
    db: Session = Depends(get_db),
):
    """返回所有未过期的、已激活的优惠券，供用户在前台领取/查看"""
    from datetime import datetime
    now = datetime.now()
    coupons = db.query(Coupon).filter(
        Coupon.active == True,
        (Coupon.expires_at == None) | (Coupon.expires_at > now)
    ).order_by(Coupon.created_at.desc()).all()
    return {
        "items": [CouponResponse.model_validate(c).model_dump() for c in coupons],
        "total": len(coupons)
    }


# 公开接口：验证优惠券码（结账时使用）
class ValidateCouponRequest(BaseModel):
    code: str

@router.post("/validate", response_model=dict)
def validate_coupon(
    request: ValidateCouponRequest,
    db: Session = Depends(get_db),
):
    """验证优惠券码是否有效，有效则返回优惠信息"""
    code = request.code
    if not code:
        raise HTTPException(status_code=400, detail="请提供优惠券码")

    from datetime import datetime
    now = datetime.now()
    coupon = db.query(Coupon).filter(
        Coupon.code == code.strip().upper(),
        Coupon.active == True,
    ).first()

    if not coupon:
        raise HTTPException(status_code=404, detail="优惠券不存在或已失效")

    if coupon.expires_at and coupon.expires_at <= now:
        raise HTTPException(status_code=400, detail="优惠券已过期")

    # 安全检查：使用次数上限
    if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
        raise HTTPException(status_code=400, detail="优惠券已用完")

    return {
        "valid": True,
        "code": coupon.code,
        "discount_type": coupon.discount_type,
        "discount_value": coupon.discount_value,
        "min_amount": coupon.min_amount,
        "message": "优惠券可用"
    }


# ============================================================
# 内部优惠券验证逻辑（供 orders.py 等模块直接调用）
# ============================================================
def _compute_coupon_discount(coupon_code: str, subtotal: float, user_id: int | None, db: Session):
    """
    验证优惠券并返回折扣金额。
    供创建订单时服务端计算订单金额使用。
    返回 (discount_amount, coupon_code_normalized)
    如果优惠券无效则抛出 HTTPException
    """
    from datetime import datetime
    from fastapi import HTTPException

    if not coupon_code:
        return 0.0, None

    now = datetime.now()
    coupon = db.query(Coupon).filter(
        Coupon.code == coupon_code.strip().upper(),
        Coupon.active == True,
    ).first()

    if not coupon:
        raise HTTPException(status_code=400, detail="优惠券不存在或已失效")

    if coupon.expires_at and coupon.expires_at <= now:
        raise HTTPException(status_code=400, detail="优惠券已过期")

    if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
        raise HTTPException(status_code=400, detail="优惠券已用完")

    if coupon.min_amount and subtotal < coupon.min_amount:
        raise HTTPException(
            status_code=400,
            detail=f"订单金额需满 {coupon.min_amount} ฿ 才能使用此优惠券"
        )

    # 计算折扣
    discount_amount = 0.0
    if coupon.discount_type == "fixed":
        discount_amount = float(coupon.discount_value)
    elif coupon.discount_type == "percent":
        discount_amount = subtotal * float(coupon.discount_value) / 100.0

    # 折扣不超过订单金额
    discount_amount = min(discount_amount, subtotal)

    # 标记已使用（乐观锁：先占一个名额）
    coupon.used_count = (coupon.used_count or 0) + 1
    db.commit()

    return round(discount_amount, 2), coupon.code


@router.get("", response_model=dict)
def get_coupons(
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    query = db.query(Coupon)

    if search:
        query = query.filter(Coupon.code.contains(search))

    total = query.count()
    coupons = query.order_by(Coupon.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [CouponResponse.model_validate(c).model_dump() for c in coupons],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.post("", response_model=dict)
def create_coupon(
    data: CouponCreate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("coupons", "create"))
):
    existing = db.query(Coupon).filter(Coupon.code == data.code.upper()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Coupon code already exists")

    coupon = Coupon(
        code=data.code.upper(),
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        min_amount=data.min_amount,
        max_uses=data.max_uses,
        expires_at=data.expires_at
    )
    db.add(coupon)
    db.commit()
    db.refresh(coupon)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="create", target_type="coupon", target_id=coupon.id,            detail=json.dumps({"key": "log_coupon_create", "code": data.code}))

    return CouponResponse.model_validate(coupon).model_dump()


@router.put("/{coupon_id}", response_model=dict)
def update_coupon(
    coupon_id: int,
    data: CouponUpdate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("coupons", "update"))
):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None and key != "code":
            setattr(coupon, key, value)

    db.commit()
    db.refresh(coupon)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="update", target_type="coupon", target_id=coupon_id,            detail=json.dumps({"key": "log_coupon_update", "coupon_id": coupon_id}))

    return CouponResponse.model_validate(coupon).model_dump()


@router.delete("/{coupon_id}", response_model=dict)
def delete_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("coupons", "delete"))
):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    db.delete(coupon)
    db.commit()

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="delete", target_type="coupon", target_id=coupon_id,            detail=json.dumps({"key": "log_coupon_delete", "coupon_id": coupon_id}))

    return {"success": True}
