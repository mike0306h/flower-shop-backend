"""
认证路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import bcrypt
from database import get_db
from models import AdminUser
from schemas import LoginRequest, LoginResponse
import sys
import os
from datetime import datetime, timedelta

# 动态从项目根目录加载 auth 模块（避免循环导入）
import importlib.util
def load_root_auth():
    backend_path = os.environ.get('BACKEND_PATH', '/app')
    spec = importlib.util.spec_from_file_location("root_auth", os.path.join(backend_path, "auth.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["root_auth"] = module
    spec.loader.exec_module(module)
    return module

root_auth = load_root_auth()
sys.modules["auth"] = root_auth  # 覆盖 auth 使其指向 root_auth，避免循环导入问题

# 从 root_auth 获取其他工具函数
create_token = root_auth.create_token
get_current_admin = root_auth.get_current_admin
get_permissions = root_auth.get_permissions
get_current_admin_optional = getattr(root_auth, 'get_current_admin_optional', None)


def _optional_admin(authorization=None):
    """同步版本的 get_current_admin_optional，供 router functions 直接使用"""
    if not authorization:
        return None
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
    except ValueError:
        return None
    import jwt
    from auth import SECRET_KEY
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None
    if "user_id" in payload and "id" not in payload:
        payload["id"] = payload["user_id"]
    if payload.get("type") == "user" and payload.get("role") in ("super_admin", "admin", "staff", "viewer"):
        return payload
    return None

# ============ 登录限流（基于数据库，进程安全） ============
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _sql_check_blocked(db: Session, username: str) -> tuple[bool, str]:
    """检查 login_attempts 表，返回 (是否被锁, 消息)"""
    row = db.execute(
        text("SELECT attempts, locked_until FROM login_attempts WHERE username = :u"),
        {"u": username.lower()}
    ).fetchone()
    if not row:
        return False, ""
    attempts, locked_until = row
    if locked_until and locked_until > datetime.utcnow():
        remaining = int((locked_until - datetime.utcnow()).total_seconds())
        return True, f"账号已锁定，请 {remaining // 60 + 1} 分钟后再试"
    # 过期记录清除
    if attempts >= MAX_ATTEMPTS or (locked_until and locked_until <= datetime.utcnow()):
        db.execute(text("DELETE FROM login_attempts WHERE username = :u"), {"u": username.lower()})
        db.commit()
    return False, ""


def _sql_record_failed(db: Session, username: str):
    """原子增加失败计数，达到上限时自动锁定"""
    uname = username.lower()
    now = datetime.utcnow()
    lock_until = now + timedelta(minutes=LOCKOUT_MINUTES) if False else None  # placeholder

    # 先查询当前值
    row = db.execute(
        text("SELECT attempts FROM login_attempts WHERE username = :u FOR UPDATE"),
        {"u": uname}
    ).fetchone()

    if not row:
        db.execute(
            text("INSERT INTO login_attempts (username, attempts, locked_until) VALUES (:u, 1, NULL)"),
            {"u": uname}
        )
        db.commit()
        return

    current_attempts = row[0]
    new_attempts = current_attempts + 1
    new_lock_until = lock_until if new_attempts >= MAX_ATTEMPTS else None

    db.execute(
        text("UPDATE login_attempts SET attempts = :a, locked_until = :lu WHERE username = :u"),
        {"a": new_attempts, "lu": new_lock_until, "u": uname}
    )
    db.commit()


def _sql_clear_attempts(db: Session, username: str):
    """登录成功后清除失败记录"""
    db.execute(text("DELETE FROM login_attempts WHERE username = :u"), {"u": username.lower()})
    db.commit()


def _sql_record_failed_atomic(db: Session, username: str):
    """原子操作：增加失败计数，达到 MAX_ATTEMPTS 则自动锁定"""
    uname = username.lower()
    now = datetime.utcnow()

    # PostgreSQL 原子 upsert：先尝试插入，冲突时更新计数+判断是否超过限制
    db.execute(
        text("""
            INSERT INTO login_attempts (username, attempts, locked_until)
            VALUES (:u, 1, NULL)
            ON CONFLICT (username) DO UPDATE SET
                attempts = login_attempts.attempts + 1,
                locked_until = CASE
                    WHEN login_attempts.attempts + 1 >= :max
                    THEN :now + INTERVAL '15 minutes'
                    ELSE NULL
                END
        """),
        {"u": uname, "max": MAX_ATTEMPTS, "now": now}
    )
    db.commit()


router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.username == request.username).first()

    # 不存在的用户名：直接返回通用错误（防用户名枚举）
    # 不记录失败（避免大量垃圾数据填满 login_attempts 表）
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 已存在的用户：先检查是否被自己之前的失败尝试锁定
    blocked, msg = _sql_check_blocked(db, request.username)
    if blocked:
        # 锁定中，但正确密码可以解锁
        if bcrypt.checkpw(request.password.encode('utf-8'), user.password_hash.encode('utf-8')):
            _sql_clear_attempts(db, request.username)
            user.last_login_at = datetime.utcnow()
            db.commit()
            token = create_token({"sub": user.username, "role": user.role, "user_id": user.id, "type": "user"})
            return LoginResponse(
                token=token,
                user={"id": user.id, "username": user.username, "role": user.role, "name": user.name},
                permissions=get_permissions(user.role),
            )
        # 密码仍错误：记录本次失败后返回锁定消息
        _sql_record_failed_atomic(db, request.username)
        raise HTTPException(status_code=429, detail=msg)

    # 用户存在+密码错：记录失败
    if not bcrypt.checkpw(request.password.encode('utf-8'), user.password_hash.encode('utf-8')):
        _sql_record_failed_atomic(db, request.username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")

    _sql_clear_attempts(db, request.username)
    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_token({"sub": user.username, "role": user.role, "user_id": user.id, "type": "user"})
    return LoginResponse(
        token=token,
        user={"id": user.id, "username": user.username, "role": user.role, "name": user.name},
        permissions=get_permissions(user.role),
    )


@router.get("/me")
def get_me(current_admin: dict = Depends(get_current_admin)):
    return {
        "username": current_admin["sub"],
        "role": current_admin["role"],
        "permissions": get_permissions(current_admin.get("role", "")),
    }


@router.post("/change-password")
def change_password(
    current_password: str,
    new_password: str,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    user = db.query(AdminUser).filter(AdminUser.username == current_admin["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not bcrypt.checkpw(current_password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=400, detail="当前密码错误")

    user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.commit()
