"""
店员管理路由（仅 super_admin 可访问）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import bcrypt
from database import get_db
from models import AdminUser, AdminLog
from schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserResponse,
    AdminUserListResponse,
)
from auth import get_current_admin, require_permission, ROLE_PERMISSIONS
from datetime import datetime


router = APIRouter()


def _log_action(db: Session, admin_id: int, admin_name: str, action: str,
                target_type: str, target_id: int, detail: str = ""):
    """写入操作日志"""
    log = AdminLog(
        admin_id=admin_id,
        admin_name=admin_name,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(log)
    db.commit()


# ============ 列表 ============
@router.get("/admin-users", response_model=AdminUserListResponse)
def list_admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str = Query(None),
    is_active: bool = Query(None),
    keyword: str = Query(None),
    current_admin: dict = Depends(require_permission("staff", "read")),
    db: Session = Depends(get_db),
):
    query = db.query(AdminUser)

    if role:
        query = query.filter(AdminUser.role == role)
    if is_active is not None:
        query = query.filter(AdminUser.is_active == is_active)
    if keyword:
        keyword = f"%{keyword}%"
        query = query.filter(
            (AdminUser.username.ilike(keyword))
            | (AdminUser.name.ilike(keyword))
            | (AdminUser.phone.ilike(keyword))
        )

    total = query.count()
    items = (
        query.order_by(AdminUser.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return AdminUserListResponse(
        total=total,
        items=[AdminUserResponse.model_validate(u) for u in items],
    )


# ============ 详情 ============
@router.get("/admin-users/{admin_id}", response_model=AdminUserResponse)
def get_admin_user(
    admin_id: int,
    current_admin: dict = Depends(require_permission("staff", "read")),
    db: Session = Depends(get_db),
):
    user = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return AdminUserResponse.model_validate(user)


# ============ 创建 ============
@router.post("/admin-users", response_model=AdminUserResponse, status_code=201)
def create_admin_user(
    data: AdminUserCreate,
    current_admin: dict = Depends(require_permission("staff", "create")),
    db: Session = Depends(get_db),
):
    # 检查用户名唯一
    existing = db.query(AdminUser).filter(AdminUser.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 密码强度
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="密码至少8位")
    if not any(c.isalpha() for c in data.password) or not any(c.isdigit() for c in data.password):
        raise HTTPException(status_code=400, detail="密码需包含字母和数字")

    # 不允许创建 super_admin
    if data.role == "super_admin":
        raise HTTPException(status_code=403, detail="无法创建超级管理员")

    user = AdminUser(
        username=data.username,
        password_hash=bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        role=data.role,
        name=data.name,
        phone=data.phone,
        department=data.department,
        created_by=current_admin.get("id"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _log_action(
        db, current_admin["id"], current_admin["sub"],
        "create", "staff", user.id,
        f"创建店员 {data.username}，角色 {data.role}"
    )

    return AdminUserResponse.model_validate(user)


# ============ 更新 ============
@router.put("/admin-users/{admin_id}", response_model=AdminUserResponse)
def update_admin_user(
    admin_id: int,
    data: AdminUserUpdate,
    current_admin: dict = Depends(require_permission("staff", "update")),
    db: Session = Depends(get_db),
):
    user = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不能修改 super_admin
    if user.role == "super_admin":
        raise HTTPException(status_code=403, detail="无法修改超级管理员")

    # 不能降级 super_admin
    if data.role == "super_admin":
        raise HTTPException(status_code=403, detail="无法设置为超级管理员")

    # 记录变化
    changes = []
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        if v is not None and getattr(user, k) != v:
            changes.append(f"{k}: {getattr(user, k)} -> {v}")
            setattr(user, k, v)

    if changes:
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        _log_action(
            db, current_admin["id"], current_admin["sub"],
            "update", "staff", user.id,
            f"更新店员 {user.username}，变更: {'; '.join(changes)}"
        )

    return AdminUserResponse.model_validate(user)


# ============ 重置密码 ============
@router.put("/admin-users/{admin_id}/reset-password")
def reset_password(
    admin_id: int,
    new_password: str,
    current_admin: dict = Depends(require_permission("staff", "update")),
    db: Session = Depends(get_db),
):
    user = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "super_admin":
        raise HTTPException(status_code=403, detail="无法重置超级管理员密码")

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="密码至少8位")
    if not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
        raise HTTPException(status_code=400, detail="密码需包含字母和数字")

    user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user.updated_at = datetime.utcnow()
    db.commit()

    _log_action(
        db, current_admin["id"], current_admin["sub"],
        "reset_password", "staff", user.id,
        f"重置店员 {user.username} 的密码"
    )

    return {"success": True, "message": "密码已重置"}


# ============ 删除 ============
@router.delete("/admin-users/{admin_id}")
def delete_admin_user(
    admin_id: int,
    current_admin: dict = Depends(require_permission("staff", "delete")),
    db: Session = Depends(get_db),
):
    user = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "super_admin":
        raise HTTPException(status_code=403, detail="无法删除超级管理员")

    # 不能删除自己
    if user.id == current_admin.get("id"):
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    username = user.username
    db.delete(user)
    db.commit()

    _log_action(
        db, current_admin["id"], current_admin["sub"],
        "delete", "staff", admin_id,
        f"删除店员 {username}"
    )

    return {"success": True, "message": "已删除"}


# ============ 获取角色列表 ============
@router.get("/admin-users/roles/list")
def list_roles(current_admin: dict = Depends(require_permission("staff", "read"))):
    """返回所有可用角色及其权限说明"""
    return {
        role: {
            "label": {
                "super_admin": "超级管理员",
                "admin": "管理员",
                "staff": "店员",
                "viewer": "查看者",
            }.get(role, role),
            "permissions": ROLE_PERMISSIONS.get(role, []),
        }
        for role in ROLE_PERMISSIONS
    }
