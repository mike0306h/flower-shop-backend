"""
管理员操作日志
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from database import get_db
from models import AdminLog
from schemas import AdminLogResponse
from auth import get_current_admin, require_permission

router = APIRouter()


def log_admin_action(db: Session, admin_id: int, admin_name: str, action: str, target_type: str, target_id: int, detail: str = None):
    """记录管理员操作"""
    log = AdminLog(
        admin_id=admin_id,
        admin_name=admin_name,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail
    )
    db.add(log)
    db.commit()


@router.get("")
def get_admin_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin_id: Optional[int] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """获取操作日志列表"""
    query = db.query(AdminLog)

    if admin_id:
        query = query.filter(AdminLog.admin_id == admin_id)
    if action:
        query = query.filter(AdminLog.action == action)
    if target_type:
        query = query.filter(AdminLog.target_type == target_type)

    total = query.count()
    logs = query.order_by(desc(AdminLog.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [AdminLogResponse.model_validate(log).model_dump() for log in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.get("/stats")
def get_log_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """获取操作统计"""
    from datetime import datetime, timedelta
    from sqlalchemy import func

    start_date = datetime.now() - timedelta(days=days)

    # 按操作类型统计
    action_stats = db.query(
        AdminLog.action,
        func.count(AdminLog.id).label('count')
    ).filter(
        AdminLog.created_at >= start_date
    ).group_by(AdminLog.action).all()

    # 按管理员统计
    admin_stats = db.query(
        AdminLog.admin_name,
        func.count(AdminLog.id).label('count')
    ).filter(
        AdminLog.created_at >= start_date
    ).group_by(AdminLog.admin_name).order_by(
        func.count(AdminLog.id).desc()
    ).limit(10).all()

    # 按目标类型统计
    type_stats = db.query(
        AdminLog.target_type,
        func.count(AdminLog.id).label('count')
    ).filter(
        AdminLog.created_at >= start_date
    ).group_by(AdminLog.target_type).all()

    return {
        "days": days,
        "action_stats": [{"action": a, "count": c} for a, c in action_stats],
        "admin_stats": [{"name": n, "count": c} for n, c in admin_stats],
        "type_stats": [{"type": t, "count": c} for t, c in type_stats]
    }


@router.delete("/cleanup")
def cleanup_old_logs(
    days: int = Query(90, ge=30, le=365),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("admin_logs", "delete")),
):
    """清理旧日志（仅 super_admin 可操作）"""
    from datetime import datetime, timedelta
    cutoff_date = datetime.now() - timedelta(days=days)
    result = db.query(AdminLog).filter(AdminLog.created_at < cutoff_date).delete()
    db.commit()
    return {"deleted": result, "message": f"已删除 {days} 天前的日志"}
