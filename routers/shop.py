"""
店铺信息 API - 前台公开读取，后台管理写入
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import ShopInfo
from schemas import ShopInfoUpdate, ShopInfoResponse
from routers.auth import get_current_admin

router = APIRouter()


@router.get("/shop-info", response_model=ShopInfoResponse)
def get_shop_info(db: Session = Depends(get_db)):
    """
    获取店铺信息（公开接口，前台页面调用）
    返回单条记录，不存在则创建默认空记录
    """
    info = db.query(ShopInfo).first()
    if not info:
        info = ShopInfo()
        db.add(info)
        db.commit()
        db.refresh(info)
    return info


@router.put("/shop-info", response_model=ShopInfoResponse)
def update_shop_info(
    data: ShopInfoUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin)
):
    """
    更新店铺信息（需管理员权限）
    """
    info = db.query(ShopInfo).first()
    if not info:
        info = ShopInfo()
        db.add(info)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(info, key, value)

    db.commit()
    db.refresh(info)
    return info
