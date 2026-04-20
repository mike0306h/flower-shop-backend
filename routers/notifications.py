"""
通知渠道管理 + 邮件发送
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from pydantic import BaseModel
from loguru import logger

from database import get_db
from models import NotificationChannel, SystemSetting
from schemas import NotificationChannelCreate, NotificationChannelUpdate, SMTPSettingUpdate
from auth import get_current_admin

router = APIRouter()


# ============ 辅助函数 ============

def mask_email(email: str) -> str:
    """邮箱脱敏"""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return local[0] + "*@..." + domain
    return local[0] + "*" * (len(local) - 2) + local[-1] + "@" + domain


# ============ 渠道管理 API ============

@router.get("/channels", response_model=dict)
def get_channels(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    type_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """获取通知渠道列表"""
    query = db.query(NotificationChannel)

    if type_filter:
        query = query.filter(NotificationChannel.type == type_filter)

    total = query.count()
    channels = query.order_by(desc(NotificationChannel.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for ch in channels:
        items.append({
            "id": ch.id,
            "type": ch.type,
            "value": ch.value,
            "value_display": mask_email(ch.value) if ch.type == "email" else ch.value,
            "name": ch.name,
            "recipient_name": ch.recipient_name,
            "enabled": ch.enabled,
            "created_at": ch.created_at
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total > 0 else 0
    }


@router.post("/channels", response_model=dict)
def create_channel(
    data: NotificationChannelCreate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """创建通知渠道"""
    if data.type != "email":
        raise HTTPException(status_code=400, detail="目前仅支持邮箱渠道")

    if "@" not in data.value:
        raise HTTPException(status_code=400, detail="请输入有效的邮箱地址")

    existing = db.query(NotificationChannel).filter(
        NotificationChannel.type == data.type,
        NotificationChannel.value == data.value
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该渠道已存在")

    channel = NotificationChannel(
        type=data.type,
        value=data.value,
        name=data.name,
        recipient_name=data.recipient_name
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)

    return {
        "id": channel.id,
        "type": channel.type,
        "value": mask_email(channel.value),
        "name": channel.name,
        "recipient_name": channel.recipient_name,
        "enabled": channel.enabled,
        "created_at": channel.created_at
    }


@router.patch("/channels/{channel_id}", response_model=dict)
def update_channel(
    channel_id: int,
    data: NotificationChannelUpdate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """更新通知渠道"""
    channel = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="渠道不存在")

    if data.type is not None and data.type != "email":
        raise HTTPException(status_code=400, detail="目前仅支持邮箱渠道")

    if data.value is not None:
        if "@" not in data.value:
            raise HTTPException(status_code=400, detail="请输入有效的邮箱地址")
        channel.value = data.value

    if data.name is not None:
        channel.name = data.name

    if data.recipient_name is not None:
        channel.recipient_name = data.recipient_name

    if data.enabled is not None:
        channel.enabled = data.enabled

    db.commit()
    db.refresh(channel)

    return {
        "id": channel.id,
        "type": channel.type,
        "value": mask_email(channel.value),
        "name": channel.name,
        "recipient_name": channel.recipient_name,
        "enabled": channel.enabled,
        "created_at": channel.created_at
    }


@router.delete("/channels/{channel_id}")
def delete_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """删除通知渠道"""
    channel = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="渠道不存在")

    db.delete(channel)
    db.commit()
    return {"success": True}


# ============ 渠道测试 API ============

class TestChannelRequest(BaseModel):
    channel_id: int
    test_message: Optional[str] = None


@router.post("/channels/test")
def test_channel(
    data: TestChannelRequest,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """测试通知渠道"""
    channel = db.query(NotificationChannel).filter(NotificationChannel.id == data.channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="渠道不存在")

    import os
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import smtplib
    import datetime

    if channel.type != "email":
        raise HTTPException(status_code=400, detail="目前仅支持测试邮箱渠道")

    test_msg = data.test_message or (
        "🧪 这是一条测试消息\n"
        "来自遇见花语管理系统\n"
        f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    smtp_host = _get_setting_db(db, "smtp_host") or os.getenv("SMTP_HOST", "")
    smtp_port = int(_get_setting_db(db, "smtp_port") or os.getenv("SMTP_PORT", "587"))
    smtp_user = _get_setting_db(db, "smtp_user") or os.getenv("SMTP_USER", "")
    smtp_password = _get_setting_db(db, "smtp_password") or os.getenv("SMTP_PASSWORD", "")
    from_email = _get_setting_db(db, "from_email") or os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        return {"success": False, "error": "SMTP 未配置，请在系统设置中配置发件邮箱"}

    try:
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = channel.value
        msg['Subject'] = "🌸 遇见花语 - 通知测试"

        html = f"""
        <html>
        <body style="font-family: Arial; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #f5af7b, #f8c6c6); padding: 20px; border-radius: 10px; text-align: center;">
                <h1 style="color: white; margin: 0;">🌸 遇见花语</h1>
            </div>
            <div style="padding: 20px; background: #fff; border: 1px solid #eee;">
                <pre style="line-height: 1.8;">{test_msg}</pre>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        return {"success": True, "message": f"测试邮件已发送到 {mask_email(channel.value)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ 系统配置 API（仅 SMTP）============

SMTP_KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "from_email"]


def _get_setting_db(db, key: str):
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return s.value if s else None


def _set_setting(db, key: str, value: str, description: str = None):
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if s:
        s.value = value
        if description:
            s.description = description
    else:
        s = SystemSetting(key=key, value=value, description=description)
        db.add(s)
    db.commit()
    return s


@router.get("/system-settings", response_model=dict)
def get_system_settings(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """获取 SMTP 配置状态（不返回明文密码）"""
    import os

    smtp_host = _get_setting_db(db, "smtp_host") or os.getenv("SMTP_HOST", "")
    smtp_port = _get_setting_db(db, "smtp_port") or os.getenv("SMTP_PORT", "587")
    smtp_user = _get_setting_db(db, "smtp_user") or os.getenv("SMTP_USER", "")
    smtp_password_db = _get_setting_db(db, "smtp_password")
    smtp_password_env = os.getenv("SMTP_PASSWORD", "")
    from_email = _get_setting_db(db, "from_email") or os.getenv("FROM_EMAIL", smtp_user)

    return {
        "smtp": {
            "host": smtp_host,
            "port": int(smtp_port) if smtp_port else 587,
            "user": smtp_user,
            "password_set": bool(smtp_password_db or smtp_password_env),
            "from_email": from_email,
            "configured": bool(smtp_host and smtp_user and (smtp_password_db or smtp_password_env)),
        }
    }


@router.put("/system-settings/smtp")
def update_smtp_settings(
    data: SMTPSettingUpdate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """更新 SMTP 配置"""
    if data.smtp_host is not None:
        _set_setting(db, "smtp_host", data.smtp_host, "SMTP 服务器地址")
    if data.smtp_port is not None:
        _set_setting(db, "smtp_port", str(data.smtp_port), "SMTP 端口")
    if data.smtp_user is not None:
        _set_setting(db, "smtp_user", data.smtp_user, "SMTP 用户名")
    if data.smtp_password is not None:
        _set_setting(db, "smtp_password", data.smtp_password, "SMTP 密码")
    if data.from_email is not None:
        _set_setting(db, "from_email", data.from_email, "发件人邮箱")

    return {"message": "SMTP 配置已更新"}


@router.post("/system-settings/smtp/test")
def test_smtp(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """测试 SMTP 连接"""
    import os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = _get_setting_db(db, "smtp_host") or os.getenv("SMTP_HOST", "")
    smtp_port = int(_get_setting_db(db, "smtp_port") or os.getenv("SMTP_PORT", "587"))
    smtp_user = _get_setting_db(db, "smtp_user") or os.getenv("SMTP_USER", "")
    smtp_password = _get_setting_db(db, "smtp_password") or os.getenv("SMTP_PASSWORD", "")
    from_email = _get_setting_db(db, "from_email") or os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        return {"success": False, "error": "SMTP 未完整配置（请填写主机、用户名、密码）"}

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
        return {"success": True, "message": f"SMTP 连接成功！已连接 {smtp_host}:{smtp_port}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── 打印机配置（飞鹅云） ────────────────────────────────────────────

class PrinterSettingUpdate(BaseModel):
    feieyun_user: Optional[str] = None
    feieyun_ukey: Optional[str] = None
    feieyun_sn: Optional[str] = None
    feieyun_auto_print: Optional[bool] = None


@router.get("/system-settings/printer")
def get_printer_settings(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """获取飞鹅打印机配置"""
    feieyun_user = _get_setting_db(db, "feieyun_user") or ""
    feieyun_ukey = _get_setting_db(db, "feieyun_ukey") or ""
    feieyun_sn = _get_setting_db(db, "feieyun_sn") or ""
    feieyun_auto_print = _get_setting_db(db, "feieyun_auto_print") == "true"

    return {
        "feieyun_user": feieyun_user,
        "feieyun_sn": feieyun_sn,
        "auto_print": feieyun_auto_print,
        "configured": bool(feieyun_user and feieyun_ukey and feieyun_sn),
    }


@router.put("/system-settings/printer")
def update_printer_settings(
    data: PrinterSettingUpdate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    """更新飞鹅打印机配置"""
    if data.feieyun_user is not None:
        _set_setting(db, "feieyun_user", data.feieyun_user, "飞鹅云用户名")
    if data.feieyun_ukey is not None:
        _set_setting(db, "feieyun_ukey", data.feieyun_ukey, "飞鹅云UKEY")
    if data.feieyun_sn is not None:
        _set_setting(db, "feieyun_sn", data.feieyun_sn, "打印机SN编号")
    if data.feieyun_auto_print is not None:
        _set_setting(db, "feieyun_auto_print", "true" if data.feieyun_auto_print else "false", "新订单自动打印")

    return {"message": "打印机配置已更新"}


@router.post("/system-settings/printer/test")
def test_printer(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    """测试打印机 — 打印一张测试页"""
    from services.feieyun import test_print as feieyun_test_print

    feieyun_user = _get_setting_db(db, "feieyun_user") or ""
    feieyun_ukey = _get_setting_db(db, "feieyun_ukey") or ""
    feieyun_sn = _get_setting_db(db, "feieyun_sn") or ""

    if not feieyun_user or not feieyun_ukey or not feieyun_sn:
        return {"success": False, "msg": "请先填写完整的打印机信息"}

    result = feieyun_test_print(feieyun_user, feieyun_ukey, feieyun_sn, lang="th")
    return result
