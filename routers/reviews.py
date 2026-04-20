"""
商品评价管理
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional
from database import get_db
from models import Review, Product, User, Order
from schemas import ReviewCreate, ReviewUpdate, ReviewResponse
from auth import get_current_user, get_current_admin

router = APIRouter()


def get_user_from_token(request) -> Optional[dict]:
    """从请求的 Authorization header 中解码 JWT，返回 payload 或 None"""
    auth = request.headers.get("authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth.replace("Bearer ", "")
    try:
        from auth import decode_token
        payload = decode_token(token)
        return payload
    except:
        return None


@router.get("")
def get_reviews(
    product_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """获取评价列表（管理员）"""
    query = db.query(Review)

    if product_id:
        query = query.filter(Review.product_id == product_id)

    if not include_inactive:
        query = query.filter(Review.active == True)

    total = query.count()
    reviews = query.order_by(desc(Review.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    # 获取用户和产品信息
    items = []
    for r in reviews:
        user = db.query(User).filter(User.id == r.user_id).first()
        product = db.query(Product).filter(Product.id == r.product_id).first()
        item = ReviewResponse.model_validate(r).model_dump()
        item["user_name"] = user.name if user else "未知用户"
        item["product_name"] = product.name if product else "未知商品"
        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.get("/product/{product_id}")
def get_product_reviews(
    product_id: int,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db)
):
    """获取单个商品的评价（公开）"""
    query = db.query(Review).filter(
        Review.product_id == product_id,
        Review.active == True
    )

    total = query.count()
    reviews = query.order_by(desc(Review.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    # 获取平均评分
    avg_result = db.query(func.avg(Review.rating)).filter(
        Review.product_id == product_id,
        Review.active == True
    ).scalar()
    avg_rating = round(float(avg_result), 1) if avg_result else 0

    # 评分分布
    rating_stats = db.query(
        Review.rating,
        func.count(Review.id)
    ).filter(
        Review.product_id == product_id,
        Review.active == True
    ).group_by(Review.rating).all()

    rating_distribution = {i: 0 for i in range(1, 6)}
    for rating, count in rating_stats:
        rating_distribution[rating] = count

    items = []
    for r in reviews:
        user = db.query(User).filter(User.id == r.user_id).first()
        item = ReviewResponse.model_validate(r).model_dump()
        item["user_name"] = user.name if user else "匿名用户"
        item["user_avatar"] = user.avatar if user else "👤"
        items.append(item)

    return {
        "items": items,
        "total": total,
        "avg_rating": avg_rating,
        "rating_distribution": rating_distribution,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.post("")
def create_review(
    data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """用户提交评价"""
    # 检查商品是否存在
    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 检查是否已评价过该商品（同一订单）
    existing = db.query(Review).filter(
        Review.product_id == data.product_id,
        Review.user_id == current_user["id"]
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="您已评价过该商品")

    # 验证评分
    if data.rating < 1 or data.rating > 5:
        raise HTTPException(status_code=400, detail="评分必须在1-5之间")

    review = Review(
        product_id=data.product_id,
        user_id=current_user["id"],
        rating=data.rating,
        comment=data.comment,
        images=data.images or [],
        is_verified=True  # 假设已验证购买
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    return ReviewResponse.model_validate(review).model_dump()


@router.put("/{review_id}")
def update_review(
    review_id: int,
    data: ReviewUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """用户修改自己的评价"""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="评价不存在")

    if review.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="无权修改此评价")

    if data.rating is not None:
        if data.rating < 1 or data.rating > 5:
            raise HTTPException(status_code=400, detail="评分必须在1-5之间")
        review.rating = data.rating

    if data.comment is not None:
        review.comment = data.comment

    if data.images is not None:
        review.images = data.images

    db.commit()
    db.refresh(review)

    return ReviewResponse.model_validate(review).model_dump()


@router.delete("/{review_id}")
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """管理员删除评价"""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="评价不存在")

    db.delete(review)
    db.commit()

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="delete", target_type="review", target_id=review_id,            detail=json.dumps({"key": "log_review_delete", "review_id": review_id}))

    return {"message": "删除成功"}


@router.patch("/{review_id}/toggle")
def toggle_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """管理员显示/隐藏评价"""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="评价不存在")

    review.active = not review.active
    db.commit()

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="update", target_type="review", target_id=review_id, detail=f"{'显示' if review.active else '隐藏'}评价 ID={review_id}")

    return {"active": review.active, "message": "已更新"}
