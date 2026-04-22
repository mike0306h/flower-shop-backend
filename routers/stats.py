"""
统计路由 - 支持多语言
"""
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import Order, Product, User, Appointment, Contact
from schemas import StatsResponse
from datetime import datetime, timedelta
from typing import Optional

router = APIRouter()

# 多语言映射
MESSAGES = {
    "zh": {
        "today_orders": "今日订单",
        "today_sales": "今日销售额",
        "total_orders": "总订单",
        "total_sales": "总销售额",
        "total_products": "商品数",
        "total_users": "用户数",
        "pending_orders": "待处理订单",
        "pending_appointments": "待处理预约",
        "pending_contacts": "待回复咨询",
        "cancellation_requests": "取消申请",
    },
    "th": {
        "today_orders": "คำสั่งซื้อวันนี้",
        "today_sales": "ยอดขายวันนี้",
        "total_orders": "คำสั่งซื้อทั้งหมด",
        "total_sales": "ยอดขายทั้งหมด",
        "total_products": "สินค้า",
        "total_users": "ผู้ใช้",
        "pending_orders": "คำสั่งซื้อที่รอดำเนินการ",
        "pending_appointments": "การนัดหมายที่รอดำเนินการ",
        "pending_contacts": "สอบถามที่รอตอบ",
        "cancellation_requests": "คำขอยกเลิก",
    },
    "en": {
        "today_orders": "Today's Orders",
        "today_sales": "Today's Sales",
        "total_orders": "Total Orders",
        "total_sales": "Total Sales",
        "total_products": "Products",
        "total_users": "Users",
        "pending_orders": "Pending Orders",
        "pending_appointments": "Pending Appointments",
        "pending_contacts": "Pending Contacts",
        "cancellation_requests": "Cancellation Requests",
    }
}


@router.get("")
def get_stats(
    accept_language: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    # 确定语言
    lang = "zh"
    if accept_language:
        if "th" in accept_language.lower():
            lang = "th"
        elif "en" in accept_language.lower():
            lang = "en"

    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    # 今日订单
    today_orders = db.query(func.count(Order.id)).filter(
        Order.created_at >= today_start,
        Order.created_at <= today_end
    ).scalar()

    # 今日销售额
    today_sales = db.query(func.sum(Order.total)).filter(
        Order.created_at >= today_start,
        Order.created_at <= today_end,
        Order.status != "cancelled"
    ).scalar() or 0

    # 总订单
    total_orders = db.query(func.count(Order.id)).scalar()

    # 总销售额
    total_sales = db.query(func.sum(Order.total)).filter(
        Order.status != "cancelled"
    ).scalar() or 0

    # 商品数
    total_products = db.query(func.count(Product.id)).scalar()

    # 用户数
    total_users = db.query(func.count(User.id)).scalar()

    # 待处理订单（包含用户申请取消的订单）
    pending_orders = db.query(func.count(Order.id)).filter(
        Order.status.in_(["pending", "confirmed", "cancellation_requested"])
    ).scalar()

    # 取消申请数量（需要管理员处理的）
    cancellation_requests = db.query(func.count(Order.id)).filter(
        Order.status == "cancellation_requested"
    ).scalar()

    # 待处理预约
    pending_appointments = db.query(func.count(Appointment.id)).filter(
        Appointment.status.in_(["pending", "confirmed"])
    ).scalar()

    # 待回复咨询
    pending_contacts = db.query(func.count(Contact.id)).filter(
        Contact.status == "pending"
    ).scalar()

    # 获取翻译后的键名
    msg = MESSAGES.get(lang, MESSAGES["zh"])

    return {
        "todayOrders": today_orders,
        "todaySales": float(today_sales),
        "totalOrders": total_orders,
        "totalSales": float(total_sales),
        "totalProducts": total_products,
        "totalUsers": total_users,
        "pendingOrders": pending_orders,
        "cancellationRequests": cancellation_requests,
        "pendingAppointments": pending_appointments,
        "pendingContacts": pending_contacts,
        "_labels": msg
    }


@router.get("/sales-chart")
def get_sales_chart(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """获取销售图表数据"""
    today = datetime.now().date()
    chart_data = []

    for i in range(days - 1, -1, -1):
        date = today - timedelta(days=i)
        date_start = datetime.combine(date, datetime.min.time())
        date_end = datetime.combine(date, datetime.max.time())

        orders_count = db.query(func.count(Order.id)).filter(
            Order.created_at >= date_start,
            Order.created_at <= date_end
        ).scalar()

        sales = db.query(func.sum(Order.total)).filter(
            Order.created_at >= date_start,
            Order.created_at <= date_end,
            Order.status != "cancelled"
        ).scalar() or 0

        chart_data.append({
            "date": date.strftime("%m-%d"),
            "orders": orders_count,
            "sales": float(sales)
        })

    return chart_data


@router.get("/low-stock")
def get_low_stock_alerts(
    db: Session = Depends(get_db)
):
    """获取库存预警列表"""
    # 查询库存低于阈值的商品
    low_stock_products = db.query(Product).filter(
        Product.stock > 0,
        Product.stock <= Product.stock_threshold,
        Product.notify_low_stock == True,
        Product.active == True
    ).all()

    # 查询库存为0的商品（严重缺货）
    out_of_stock_products = db.query(Product).filter(
        Product.stock == 0,
        Product.active == True
    ).all()

    return {
        "low_stock": [
            {
                "id": p.id,
                "name": p.name,
                "stock": p.stock,
                "threshold": p.stock_threshold,
                "category": p.category
            }
            for p in low_stock_products
        ],
        "out_of_stock": [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category
            }
            for p in out_of_stock_products
        ],
        "total_low_stock": len(low_stock_products),
        "total_out_of_stock": len(out_of_stock_products)
    }
