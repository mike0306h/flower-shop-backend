"""
通知服务 - 邮件通知
支持向多个管理员账号发送邮件通知
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx
from loguru import logger


# ============ DB 配置读取（DB 优先，环境变量作后备）============

def _get_smtp_config(db=None):
    """获取 SMTP 配置"""
    from models import SystemSetting
    if db is None:
        from database import SessionLocal
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    try:
        def get_val(key, default=""):
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            return row.value if row else default
        return {
            "host": get_val("smtp_host", os.getenv("SMTP_HOST", "")),
            "port": int(get_val("smtp_port", os.getenv("SMTP_PORT", "587"))),
            "user": get_val("smtp_user", os.getenv("SMTP_USER", "")),
            "password": get_val("smtp_password", os.getenv("SMTP_PASSWORD", "")),
            "from_email": get_val("from_email", os.getenv("FROM_EMAIL", "")),
        }
    finally:
        if should_close:
            db.close()


# ============ 辅助函数 ============

def mask_email(email: str) -> str:
    """邮箱脱敏显示"""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"

# ============ Email 发送 ============

def send_email(to_email: str, subject: str, html_content: str, db=None) -> bool:
    """发送 Email（支持HTML）。db 参数可选，传入则优先读 DB 配置"""
    cfg = _get_smtp_config(db)
    smtp_host = cfg["host"]
    smtp_user = cfg["user"]
    smtp_password = cfg["password"]
    from_email = cfg["from_email"] or smtp_user

    if not smtp_host or not smtp_user or not smtp_password:
        logger.warning("Email not configured, skipping email send")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #f5af7b 0%, #f8c6c6 100%); padding: 30px; border-radius: 20px 20px 0 0;">
                <h1 style="color: white; text-align: center; margin: 0;">🌸 遇见花语</h1>
            </div>
            <div style="padding: 30px; background: #fff; border: 1px solid #eee; border-top: none;">
                {html_content}
            </div>
            <div style="text-align: center; padding: 20px; color: #999; font-size: 12px; background: #f9f9f9; border-radius: 0 0 20px 20px;">
                <p>© 2024 遇见花语 Floral Shop. All rights reserved.</p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(smtp_host, cfg["port"]) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info(f"Email sent to {mask_email(to_email)}")
        return True

    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


# ============ 多渠道通知核心函数 ============

def get_enabled_channels(db) -> list:
    """从数据库获取所有已启用的通知渠道"""
    from models import NotificationChannel
    try:
        channels = db.query(NotificationChannel).filter(NotificationChannel.enabled == True).all()
        return channels
    except Exception as e:
        logger.error(f"Failed to get notification channels: {e}")
        return []


def notify_admins(db, channels: list, subject: str, html_content: str) -> dict:
    """
    向所有启用的管理员渠道发送通知
    返回发送结果统计
    """
    results = {"email": {"success": 0, "failed": 0}}

    for ch in channels:
        if ch.type == "email":
            ok = send_email(ch.value, subject, html_content, db)
            if ok:
                results["email"]["success"] += 1
            else:
                results["email"]["failed"] += 1

    return results


# ============ 订单通知 ============

def build_order_html(order_data: dict, lang: str = "zh") -> str:
    """构建订单通知的 HTML"""
    status_map = {
        "zh": {
            "pending": "📋 待确认",
            "confirmed": "✅ 已确认",
            "preparing": "🌸 制作中",
            "shipped": "🚚 已发货",
            "delivered": "📦 已送达",
            "cancelled": "❌ 已取消"
        },
        "th": {
            "pending": "📋 รอตรวจสอบ",
            "confirmed": "✅ ยืนยันแล้ว",
            "preparing": "🌸 กำลังจัดทำ",
            "shipped": "🚚 จัดส่งแล้ว",
            "delivered": "📦 ส่งถึงแล้ว",
            "cancelled": "❌ ถูกยกเลิก"
        }
    }

    order_no = order_data.get("order_no", "")
    status = order_data.get("status", "")
    user_name = order_data.get("user_name", "—")
    total = order_data.get("total", 0)
    phone = order_data.get("phone", "—")
    address = order_data.get("address", "—")
    items = order_data.get("items", [])
    time_slot = order_data.get("time_slot", "")
    note = order_data.get("note", "")

    texts = status_map.get(lang, status_map["zh"])
    status_text = texts.get(status, status)

    items_html = ""
    for item in items:
        items_html += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{item.get('name', '')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">x{item.get('quantity', 1)}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">฿{item.get('price', 0):.2f}</td>
        </tr>
        """

    html = f"""
    <div style="background: #fff3e0; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="margin: 0 0 5px; color: #e65100;">🛒 新订单通知</h2>
        <p style="margin: 0; color: #666; font-size: 14px;">New Order Notification</p>
    </div>

    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr>
            <td style="padding: 10px; background: #f5f5f5; border-radius: 8px;" colspan="3">
                <strong>📝 订单号:</strong> {order_no}<br>
                <strong>📌 状态:</strong> {status_text}<br>
                <strong>👤 客户:</strong> {user_name}<br>
                <strong>📞 电话:</strong> {phone}<br>
                <strong>💰 总计:</strong> <span style="color: #e91e63; font-size: 18px;">฿{total:.2f}</span>
            </td>
        </tr>
    </table>

    <h3 style="border-bottom: 2px solid #f5af7b; padding-bottom: 8px;">📦 商品明细</h3>
    <table style="width: 100%; border-collapse: collapse;">
        <thead>
            <tr style="background: #f5f5f5;">
                <th style="padding: 8px; text-align: left;">商品</th>
                <th style="padding: 8px; text-align: center;">数量</th>
                <th style="padding: 8px; text-align: right;">价格</th>
            </tr>
        </thead>
        <tbody>
            {items_html}
        </tbody>
        <tfoot>
            <tr>
                <td colspan="2" style="padding: 10px; text-align: right; font-weight: bold;">总计:</td>
                <td style="padding: 10px; text-align: right; font-weight: bold; color: #e91e63;">฿{total:.2f}</td>
            </tr>
        </tfoot>
    </table>

    <h3 style="border-bottom: 2px solid #f5af7b; padding-bottom: 8px; margin-top: 20px;">🚚 配送信息</h3>
    <p style="margin: 5px 0;"><strong>📍 地址:</strong> {address}</p>
    <p style="margin: 5px 0;"><strong>⏰ 时段:</strong> {time_slot or '—'}</p>
    <p style="margin: 5px 0;"><strong>📝 备注:</strong> {note or '—'}</p>
    """
    return html


def send_order_notification(db, order_data: dict, lang: str = "zh") -> dict:
    """发送订单通知给所有管理员"""
    channels = get_enabled_channels(db)
    if not channels:
        logger.info("No notification channels configured, skipping order notification")
        return {"sent": False, "reason": "no_channels"}

    html = build_order_html(order_data, lang)
    results = notify_admins(db, channels, f"🌸 新订单 - {order_data.get('order_no', '')}", html)
    return {"sent": True, **results}


# ============ 预约通知 ============

def build_appointment_html(data: dict, lang: str = "zh") -> str:
    """构建预约通知的 HTML"""
    occasion_map = {
        "zh": {"birthday": "生日", "wedding": "婚礼", "anniversary": "纪念日", "funeral": "葬礼", "business": "商务", "other": "其他"},
        "th": {"birthday": "วันเกิด", "wedding": "งานแต่งงาน", "anniversary": "ครบรอบ", "funeral": "งานศพ", "business": "ธุรกิจ", "other": "อื่นๆ"}
    }
    status_map = {
        "zh": {"pending": "待确认", "confirmed": "已确认", "completed": "已完成", "cancelled": "已取消"},
        "th": {"pending": "รอตรวจสอบ", "confirmed": "ยืนยันแล้ว", "completed": "เสร็จสิ้น", "cancelled": "ถูกยกเลิก"}
    }

    occ_texts = occasion_map.get(lang, occasion_map["zh"])
    sta_texts = status_map.get(lang, status_map["zh"])

    appt_no = data.get("appointment_no", "")
    occasion = data.get("occasion", "")
    occasion_text = occ_texts.get(occasion, occasion)
    status = data.get("status", "pending")
    status_text = sta_texts.get(status, status)
    customer_name = data.get("customer_name", "—")
    customer_phone = data.get("customer_phone", "—")
    budget = data.get("budget", "—")
    delivery_date = data.get("delivery_date", "—")
    delivery_time = data.get("delivery_time", "—")
    recipient_name = data.get("recipient_name", "—")
    recipient_phone = data.get("recipient_phone", "—")
    delivery_address = data.get("delivery_address", "—")
    requirements = data.get("requirements", "")
    blessing_card = data.get("blessing_card", "")
    packaging = data.get("packaging", "")
    callback_time = data.get("callback_time", "")

    html = f"""
    <div style="background: #e8f5e9; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="margin: 0 0 5px; color: #2e7d32;">📅 新预约通知</h2>
        <p style="margin: 0; color: #666; font-size: 14px;">New Appointment Notification</p>
    </div>

    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr>
            <td style="padding: 10px; background: #f5f5f5; border-radius: 8px;" colspan="2">
                <strong>📋 预约号:</strong> {appt_no}<br>
                <strong>📌 状态:</strong> {status_text}<br>
                <strong>🎉 场合:</strong> {occasion_text}<br>
                <strong>💰 预算:</strong> {budget}
            </td>
        </tr>
    </table>

    <h3 style="border-bottom: 2px solid #81c784; padding-bottom: 8px;">👤 客户信息</h3>
    <p style="margin: 5px 0;"><strong>👤 姓名:</strong> {customer_name}</p>
    <p style="margin: 5px 0;"><strong>📞 电话:</strong> {customer_phone}</p>
    <p style="margin: 5px 0;"><strong>⏰ 期望回电:</strong> {callback_time or '—'}</p>

    <h3 style="border-bottom: 2px solid #81c784; padding-bottom: 8px; margin-top: 20px;">🎁 配送信息</h3>
    <p style="margin: 5px 0;"><strong>📅 配送日期:</strong> {delivery_date} {delivery_time}</p>
    <p style="margin: 5px 0;"><strong>👤 收件人:</strong> {recipient_name}</p>
    <p style="margin: 5px 0;"><strong>📞 收件电话:</strong> {recipient_phone}</p>
    <p style="margin: 5px 0;"><strong>📍 配送地址:</strong> {delivery_address}</p>
    <p style="margin: 5px 0;"><strong>📦 包装:</strong> {packaging or '—'}</p>

    <h3 style="border-bottom: 2px solid #81c784; padding-bottom: 8px; margin-top: 20px;">💝 祝福卡片</h3>
    <p style="background: #fff9c4; padding: 15px; border-radius: 8px; font-style: italic;">{blessing_card or '—'}</p>

    <h3 style="border-bottom: 2px solid #81c784; padding-bottom: 8px; margin-top: 20px;">📝 特殊要求</h3>
    <p style="background: #f5f5f5; padding: 15px; border-radius: 8px;">{requirements or '—'}</p>
    """
    return html


def send_appointment_notification(db, appointment_data: dict, lang: str = "zh") -> dict:
    """发送预约通知给所有管理员"""
    channels = get_enabled_channels(db)
    if not channels:
        logger.info("No notification channels configured, skipping appointment notification")
        return {"sent": False, "reason": "no_channels"}

    html = build_appointment_html(appointment_data, lang)
    results = notify_admins(db, channels, f"📅 新预约 - {appointment_data.get('appointment_no', '')}", html)
    return {"sent": True, **results}


# ============ 联系我们通知 ============

def build_contact_html(data: dict, lang: str = "zh") -> str:
    """构建联系我们通知的 HTML"""
    name = data.get("name", "—")
    phone = data.get("phone", "—")
    message = data.get("message", "")

    html = f"""
    <div style="background: #e3f2fd; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="margin: 0 0 5px; color: #1565c0;">📞 联系我们通知</h2>
        <p style="margin: 0; color: #666; font-size: 14px;">Contact Us Notification</p>
    </div>

    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr>
            <td style="padding: 10px; background: #f5f5f5; border-radius: 8px;" colspan="2">
                <strong>👤 姓名:</strong> {name}<br>
                <strong>📞 电话:</strong> {phone}
            </td>
        </tr>
    </table>

    <h3 style="border-bottom: 2px solid #64b5f6; padding-bottom: 8px;">💬 留言内容</h3>
    <p style="background: #f5f5f5; padding: 15px; border-radius: 8px; line-height: 1.8;">{message}</p>
    """
    return html


def send_contact_notification(db, contact_data: dict, lang: str = "zh") -> dict:
    """发送联系我们通知给所有管理员"""
    channels = get_enabled_channels(db)
    if not channels:
        logger.info("No notification channels configured, skipping contact notification")
        return {"sent": False, "reason": "no_channels"}

    html = build_contact_html(contact_data, lang)
    results = notify_admins(db, channels, f"📞 联系我们 - {contact_data.get('name', '')}", html)
    return {"sent": True, **results}


# ============ 欢迎邮件 ============

def send_welcome_email(to_email: str, name: str, level: str = "normal") -> bool:
    """发送欢迎邮件"""
    level_names = {
        "zh": {"normal": "普通会员", "silver": "银卡会员", "gold": "金卡会员", "diamond": "钻卡会员"},
        "th": {"normal": "สมาชิกทั่วไป", "silver": "สมาชิกเงิน", "gold": "สมาชิกทอง", "diamond": "สมาชิกเพชร"}
    }

    texts = level_names.get("zh", level_names["zh"])
    level_text = texts.get(level, texts["normal"])

    subject = f"🌸 欢迎加入遇见花语 - 您已成为{level_text}"
    html_content = f"""
    <p style="font-size: 16px; line-height: 1.8;">
        亲爱的 <strong>{name}</strong>，<br><br>
        欢迎加入遇见花语！<br><br>
        您已成为我们的<strong>{level_text}</strong>，享受以下权益：
    </p>
    <ul style="line-height: 2;">
        <li>消费积分奖励</li>
        <li>会员专属折扣</li>
        <li>优先客服通道</li>
    </ul>
    <p style="margin-top: 20px;">感谢您的信任！</p>
    <p>遇见花语团队</p>
    """

    return send_email(to_email, subject, html_content)
