"""
商品分类路由（多语言 + 排序）
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import asc
from typing import Optional, List
from database import get_db
from models import Category
from schemas import CategoryCreate, CategoryUpdate, CategoryResponse
from auth import get_current_admin, require_permission

router = APIRouter()


@router.get("", response_model=List[CategoryResponse])
def get_categories(
    active_only: bool = Query(False, description="仅返回激活的分类"),
    db: Session = Depends(get_db)
):
    """获取所有分类（按 sort_order 升序排列）"""
    query = db.query(Category)
    if active_only:
        query = query.filter(Category.active == True)
    categories = query.order_by(asc(Category.sort_order)).all()
    return [CategoryResponse.model_validate(c) for c in categories]


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: Session = Depends(get_db)):
    """获取单个分类"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    return CategoryResponse.model_validate(category)


@router.post("", response_model=CategoryResponse)
def create_category(category_data: CategoryCreate, db: Session = Depends(get_db), current_admin: dict = Depends(require_permission("categories", "create"))):
    """创建分类"""
    # 检查 slug 是否重复
    existing = db.query(Category).filter(Category.slug == category_data.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"分类 slug「{category_data.slug}」已存在")

    category = Category(
        slug=category_data.slug,
        name_zh=category_data.name_zh,
        name_th=category_data.name_th,
        name_en=category_data.name_en,
        image=category_data.image,
        emoji=category_data.emoji,
        sort_order=category_data.sort_order,
        active=category_data.active,
        show_on_home=category_data.show_on_home,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="create", target_type="category", target_id=category.id,            detail=json.dumps({"key": "log_category_create", "name": category_data.name_zh}))

    return CategoryResponse.model_validate(category)


@router.put("/{category_id}", response_model=CategoryResponse)
@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, update_data: CategoryUpdate, db: Session = Depends(get_db), current_admin: dict = Depends(require_permission("categories", "update"))):
    """更新分类"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")

    update_dict = update_data.model_dump(exclude_unset=True)

    # 如果更新 slug，检查唯一性
    if "slug" in update_dict:
        new_slug = update_dict["slug"]
        existing = db.query(Category).filter(
            Category.slug == new_slug,
            Category.id != category_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"分类 slug「{new_slug}」已被其他分类使用")

    for key, value in update_dict.items():
        setattr(category, key, value)

    db.commit()
    db.refresh(category)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="update", target_type="category", target_id=category_id,            detail=json.dumps({"key": "log_category_update", "category_id": category_id}))

    return CategoryResponse.model_validate(category)


@router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(require_permission("categories", "delete"))):
    """删除分类"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")

    db.delete(category)
    db.commit()

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="delete", target_type="category", target_id=category_id,            detail=json.dumps({"key": "log_category_delete", "category_id": category_id}))

    return {"message": "分类已删除"}
