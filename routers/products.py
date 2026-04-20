"""
商品路由
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from database import get_db
from models import Product
from schemas import ProductCreate, ProductUpdate, ProductResponse
from auth import get_current_admin, require_permission

router = APIRouter()


@router.get("")
def get_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Product)

    if category:
        query = query.filter(Product.category == category)

    if active is not None:
        query = query.filter(Product.active == active)

    if search:
        query = query.filter(
            (Product.name.contains(search)) |
            (Product.name_th.contains(search)) |
            (Product.name_en.contains(search))
        )

    total = query.count()
    products = query.order_by(desc(Product.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [ProductResponse.model_validate(p).model_dump() for p in products],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return ProductResponse.model_validate(product).model_dump()


@router.post("")
def create_product(product_data: ProductCreate, db: Session = Depends(get_db), current_admin: dict = Depends(require_permission("products", "create"))):
    product = Product(
        name=product_data.name,
        name_th=product_data.name_th,
        name_en=product_data.name_en,
        description=product_data.description,
        description_th=product_data.description_th,
        description_en=product_data.description_en,
        price=product_data.price,
        original_price=product_data.original_price,
        images=product_data.images,
        stock=product_data.stock,
        stock_threshold=product_data.stock_threshold,
        notify_low_stock=product_data.notify_low_stock,
        category=product_data.category,
        tags=product_data.tags,
        flower_options=product_data.flower_options,
        language=product_data.language,
        active=product_data.active
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="create", target_type="product", target_id=product.id,            detail=json.dumps({"key": "log_product_create", "name": product_data.name}))

    return ProductResponse.model_validate(product).model_dump()


@router.put("/{product_id}")
@router.patch("/{product_id}")
def update_product(product_id: int, update_data: ProductUpdate, db: Session = Depends(get_db), current_admin: dict = Depends(require_permission("products", "update"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="update", target_type="product", target_id=product_id,            detail=json.dumps({"key": "log_product_update", "product_id": product_id}))

    return ProductResponse.model_validate(product).model_dump()


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(require_permission("products", "delete"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    db.delete(product)
    db.commit()

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="delete", target_type="product", target_id=product_id,            detail=json.dumps({"key": "log_product_delete", "product_id": product_id}))

    return {"message": "商品已删除"}
