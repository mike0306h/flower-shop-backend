"""
JWT 认证模块
"""
from datetime import datetime, timedelta
from typing import Optional, List
import secrets
import bcrypt
import jwt
import os
from fastapi import Depends, HTTPException, Header

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    # 仅在本地开发/测试时自动生成，生产环境必须设置环境变量
    SECRET_KEY = secrets.token_urlsafe(64)
    print(f"[WARN] SECRET_KEY not set, using auto-generated key (not suitable for production)")

# 确保密钥足够长（JWT 推荐至少 32 字节）
if len(SECRET_KEY) < 32:
    raise ValueError("SECRET_KEY must be at least 32 characters")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 days

# ============ 登录限流（已迁移至数据库，routers/auth.py 使用 SQL 版本） ============

# ============ 权限定义 ============
ROLE_PERMISSIONS = {
    "super_admin": [
        # 仪表盘
        "dashboard:read",
        # 订单
        "orders:read", "orders:update", "orders:delete", "orders:cancel",
        # 商品
        "products:read", "products:create", "products:update", "products:delete",
        # 分类
        "categories:read", "categories:create", "categories:update", "categories:delete",
        # 优惠券
        "coupons:read", "coupons:create", "coupons:update", "coupons:delete",
        # 评价
        "reviews:read", "reviews:update", "reviews:delete",
        # 报表
        "reports:read", "reports:export",
        # 日志
        "admin_logs:read", "admin_logs:delete",
        # 用户
        "users:read", "users:update", "users:delete",
        # 预约
        "appointments:read", "appointments:update", "appointments:delete",
        # 咨询
        "contacts:read", "contacts:update", "contacts:delete",
        # 店员管理（仅 super_admin 可访问）
        "staff:read", "staff:create", "staff:update", "staff:delete",
        # 系统设置
        "settings:read", "settings:update",
        # 店铺信息
        "shop_info:read", "shop_info:update",
        # 通知
        "notifications:read", "notifications:update",
        # 数据导出
        "export:read", "export:create",
    ],
    "admin": [
        "dashboard:read",
        "orders:read", "orders:update", "orders:cancel",
        "products:read", "products:create", "products:update",
        "categories:read", "categories:create", "categories:update",
        "coupons:read", "coupons:create", "coupons:update",
        "reviews:read", "reviews:update",
        "reports:read", "reports:export",
        "admin_logs:read",
        "users:read", "users:update",
        "appointments:read", "appointments:update",
        "contacts:read", "contacts:update",
        "notifications:read", "notifications:update",
        "settings:read",
        "export:read", "export:create",
    ],
    "staff": [
        "dashboard:read",
        "orders:read", "orders:update",
        "products:read",
        "coupons:read",
        "reviews:read", "reviews:update",
        "reports:read",
        "appointments:read", "appointments:update",
        "contacts:read", "contacts:update",
        "settings:read",
    ],
    "viewer": [
        "dashboard:read",
        "orders:read",
        "products:read",
        "reports:read",
        "settings:read",
    ],
}


def get_permissions(role: str) -> List[str]:
    """根据角色返回权限列表"""
    return ROLE_PERMISSIONS.get(role, [])


def has_permission(role: str, module: str, action: str = "read") -> bool:
    """检查角色是否有指定模块+动作的权限"""
    perm = f"{module}:{action}"
    return perm in ROLE_PERMISSIONS.get(role, [])


def require_permission(module: str, action: str = "read"):
    """FastAPI 依赖项：检查当前用户是否有指定权限"""
    def checker(current_admin: dict = Depends(get_current_admin)) -> dict:
        role = current_admin.get("role", "")
        if not has_permission(role, module, action):
            raise HTTPException(status_code=403, detail=f"没有 [{module}:{action}] 权限")
        return current_admin
    return checker


def create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def get_current_admin(authorization: str = Header(None)) -> dict:
    """FastAPI 依赖项：从 Authorization header 获取当前管理员"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证 token")

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="无效的认证方式")
    except ValueError:
        raise HTTPException(status_code=401, detail="无效的认证格式")

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 已过期或无效")

    # 统一 id 字段（login 时用 user_id，normalize 为 id）
    if "user_id" in payload and "id" not in payload:
        payload["id"] = payload["user_id"]

    # 检查是否是用户 token
    if payload.get("type") != "user":
        raise HTTPException(status_code=401, detail="无效的 token 类型")

    return payload


async def get_current_admin_optional(authorization: str = Header(None)) -> Optional[dict]:
    """获取当前管理员，如果未登录或非管理员返回 None"""
    if not authorization:
        return None

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
    except ValueError:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    # 统一 id 字段
    if "user_id" in payload and "id" not in payload:
        payload["id"] = payload["user_id"]

    if payload.get("role") == "admin":
        return payload
    return None


async def get_current_user_optional(authorization: str = Header(None)) -> Optional[dict]:
    """获取当前用户，如果未登录返回 None"""
    if not authorization:
        return None

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
    except ValueError:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    if "user_id" in payload and "id" not in payload:
        payload["id"] = payload["user_id"]

    if payload.get("type") == "user":
        return payload
    return None


async def get_current_user(authorization: str = Header(None)) -> dict:
    """获取当前登录用户，未登录抛出异常"""
    result = await get_current_user_optional(authorization)
    if not result:
        raise HTTPException(status_code=401, detail="请先登录")
    return result
