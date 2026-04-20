"""
邮箱验证路由 - 注册验证 + 找回密码
"""
import secrets
import hashlib
import bcrypt
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models import User, EmailVerification
from schemas import (
    SendVerifyEmailRequest, SendResetPasswordEmailRequest,
    ResetPasswordRequest, VerifyEmailRequest, VerifyEmailResponse, SendEmailResponse
)
from services.notification import send_email

router = APIRouter()


def generate_code():
    """生成6位数字验证码"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])


def hash_code(code: str) -> str:
    """验证码哈希"""
    return hashlib.sha256(code.encode()).hexdigest()


def mask_email(email: str) -> str:
    """邮箱脱敏"""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def get_frontend_base_url():
    """获取前端基础URL"""
    import os
    return os.getenv("FRONTEND_BASE_URL", "https://bkkflowers.com")


def can_resend(db: Session, email: str) -> tuple[bool, str]:
    """检查是否可以重新发送验证码（60秒限制）"""
    recent = db.query(EmailVerification).filter(
        EmailVerification.email == email,
        EmailVerification.created_at >= datetime.utcnow() - timedelta(seconds=60)
    ).first()
    if recent:
        remaining = 60 - int((datetime.utcnow() - recent.created_at).total_seconds())
        return False, f"请 {remaining} 秒后再试"
    return True, ""


def build_verify_email_html(email: str, verify_url: str, code: str) -> str:
    """构建注册验证邮件HTML"""
    return f"""
    <div style="background: #fff3e0; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="margin: 0 0 5px; color: #e65100;">🌸 邮箱验证</h2>
        <p style="margin: 0; color: #666; font-size: 14px;">Email Verification</p>
    </div>
    <p style="font-size: 16px; line-height: 1.8;">
        亲爱的用户，您好！<br><br>
        感谢您注册遇见花语！请点击以下链接验证您的邮箱：
    </p>
    <div style="text-align: center; margin: 30px 0;">
        <a href="{verify_url}" style="display: inline-block; background: linear-gradient(135deg, #f5af7b, #f8c6c6); color: white; padding: 15px 40px; border-radius: 30px; text-decoration: none; font-size: 16px; font-weight: bold;">
            验证邮箱
        </a>
    </div>
    <p style="color: #666; font-size: 14px;">
        或者复制以下链接到浏览器打开：<br>
        <a href="{verify_url}" style="color: #f5af7b; word-break: break-all;">{verify_url}</a>
    </p>
    <p style="background: #f5f5f5; padding: 15px; border-radius: 8px; font-size: 14px; color: #666;">
        ⏰ 此链接 <strong>5 分钟</strong>内有效<br>
        🔐 验证码：<strong>{code}</strong>
    </p>
    <p style="color: #999; font-size: 12px; margin-top: 20px;">
        如果您没有注册过遇见花语，请忽略此邮件。<br>
        此邮件由系统自动发送，请勿回复。
    </p>
    """


@router.post("/send-verify-email", response_model=SendEmailResponse)
def send_verify_email(data: SendVerifyEmailRequest, db: Session = Depends(get_db)):
    """发送注册验证邮件"""
    can_send, msg = can_resend(db, data.email)
    if not can_send:
        raise HTTPException(status_code=429, detail=msg)

    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    code = generate_code()
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    verification = EmailVerification(
        email=data.email,
        code=hash_code(code),
        type="register",
        user_id=None,
        expires_at=expires_at
    )
    db.add(verification)
    db.commit()

    base_url = get_frontend_base_url()
    verify_url = f"{base_url}/auth/verify-email?code={code}"
    html = build_verify_email_html(data.email, verify_url, code)

    ok = send_email(data.email, "🌸 请验证您的邮箱 - 遇见花语", html, db)

    if ok:
        return SendEmailResponse(success=True, message=f"验证邮件已发送到 {mask_email(data.email)}")
    else:
        raise HTTPException(status_code=500, detail="邮件发送失败，请检查邮箱地址或稍后重试")


@router.post("/verify-email", response_model=VerifyEmailResponse)
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    """验证邮箱验证码（注册流程第二步）"""
    # 对输入的验证码进行哈希后查询
    code_hash = hash_code(data.code)
    verification = db.query(EmailVerification).filter(
        EmailVerification.code == code_hash,
        EmailVerification.type == "register",
        EmailVerification.used == False,
        EmailVerification.expires_at > datetime.utcnow()
    ).first()

    if not verification:
        raise HTTPException(status_code=400, detail="验证码无效或已过期")

    verification.used = True
    db.commit()

    return VerifyEmailResponse(
        success=True,
        message="邮箱验证成功",
        user={"email": verification.email}
    )


def build_reset_password_email_html(email: str, reset_url: str, code: str) -> str:
    """构建重置密码邮件HTML"""
    return f"""
    <div style="background: #e3f2fd; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="margin: 0 0 5px; color: #1565c0;">🔑 密码重置</h2>
        <p style="margin: 0; color: #666; font-size: 14px;">Password Reset</p>
    </div>
    <p style="font-size: 16px; line-height: 1.8;">
        亲爱的用户，您好！<br><br>
        我们收到了您的密码重置请求。请点击以下链接设置新密码：
    </p>
    <div style="text-align: center; margin: 30px 0;">
        <a href="{reset_url}" style="display: inline-block; background: linear-gradient(135deg, #1976d2, #42a5f5); color: white; padding: 15px 40px; border-radius: 30px; text-decoration: none; font-size: 16px; font-weight: bold;">
            重置密码
        </a>
    </div>
    <p style="color: #666; font-size: 14px;">
        或者复制以下链接到浏览器打开：<br>
        <a href="{reset_url}" style="color: #1976d2; word-break: break-all;">{reset_url}</a>
    </p>
    <p style="background: #f5f5f5; padding: 15px; border-radius: 8px; font-size: 14px; color: #666;">
        ⏰ 此链接 <strong>5 分钟</strong>内有效<br>
        🔐 验证码：<strong>{code}</strong>
    </p>
    <p style="color: #e91e63; font-size: 14px; margin-top: 20px;">
        ⚠️ 如果您未发起密码重置请求，请忽略此邮件，您的账号安全不会受到影响。
    </p>
    """


@router.post("/send-reset-password-email", response_model=SendEmailResponse)
def send_reset_password_email(data: SendResetPasswordEmailRequest, db: Session = Depends(get_db)):
    """发送重置密码邮件"""
    can_send, msg = can_resend(db, data.email)
    if not can_send:
        raise HTTPException(status_code=429, detail=msg)

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        # 安全考虑：不提示邮箱不存在
        return SendEmailResponse(success=True, message="如果邮箱已注册，重置链接已发送到您的邮箱")

    code = generate_code()
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    verification = EmailVerification(
        email=data.email,
        code=hash_code(code),
        type="reset_password",
        user_id=user.id,
        expires_at=expires_at
    )
    db.add(verification)
    db.commit()

    base_url = get_frontend_base_url()
    reset_url = f"{base_url}/auth/reset-password?code={code}"
    html = build_reset_password_email_html(data.email, reset_url, code)

    ok = send_email(data.email, "🔑 密码重置链接 - 遇见花语", html, db)

    if ok:
        return SendEmailResponse(success=True, message=f"重置链接已发送到 {mask_email(data.email)}")
    else:
        raise HTTPException(status_code=500, detail="邮件发送失败，请稍后重试")


@router.post("/reset-password", response_model=VerifyEmailResponse)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """验证验证码并重置密码"""
    code_hash = hash_code(data.code)
    verification = db.query(EmailVerification).filter(
        EmailVerification.code == code_hash,
        EmailVerification.type == "reset_password",
        EmailVerification.used == False,
        EmailVerification.expires_at > datetime.utcnow()
    ).first()

    if not verification:
        raise HTTPException(status_code=400, detail="验证码无效或已过期")

    user = db.query(User).filter(User.id == verification.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.password_hash = bcrypt.hashpw(data.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    verification.used = True
    db.commit()

    return VerifyEmailResponse(
        success=True,
        message="密码重置成功",
        user={"email": verification.email}
    )
