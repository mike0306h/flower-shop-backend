"""
销售报表统计
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, text
from datetime import datetime, timedelta
from database import get_db
from models import Order, Product, User
from auth import get_current_admin, require_permission

router = APIRouter()


@router.get("/sales-report")
def get_sales_report(
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("reports", "read"))
):
    """
    销售报表
    - daily: 按日统计（最近30天）
    - weekly: 按周统计（最近12周）
    - monthly: 按月统计（最近12个月）
    """
    today = datetime.now().date()

    if period == "daily":
        # 最近30天按日统计
        start_date = today - timedelta(days=29)
        date_format = "%m-%d"
        group_by = func.date(Order.created_at)

    elif period == "weekly":
        # 最近12周按周统计
        start_date = today - timedelta(weeks=11)
        # 找到本周一
        start_date = start_date - timedelta(days=start_date.weekday())
        date_format = "%Y-W%W"
        group_by = func.date_trunc('week', Order.created_at)

    else:  # monthly
        # 最近12个月按月统计
        start_date = today.replace(day=1) - timedelta(days=365)
        date_format = "%Y-%m"
        group_by = func.date_trunc('month', Order.created_at)

    # 查询统计数据
    query = db.query(
        group_by.label('date'),
        func.count(Order.id).label('order_count'),
        func.sum(Order.total).label('total_sales'),
        func.avg(Order.total).label('avg_order_value')
    ).filter(
        Order.status.notin_(['cancelled', 'pending']),
        Order.created_at >= start_date
    ).group_by(group_by).order_by(group_by)

    results = query.all()

    # 格式化数据
    data = []
    for r in results:
        date_val = r.date
        if isinstance(date_val, datetime):
            date_str = date_val.strftime(date_format)
        else:
            date_str = str(date_val)[:10]

        data.append({
            "date": date_str,
            "orders": r.order_count or 0,
            "sales": float(r.total_sales or 0),
            "avg_value": float(r.avg_order_value or 0)
        })

    # 计算总计
    total_orders = sum(d["orders"] for d in data)
    total_sales = sum(d["sales"] for d in data)
    avg_order = total_sales / total_orders if total_orders > 0 else 0

    return {
        "period": period,
        "data": data,
        "summary": {
            "total_orders": total_orders,
            "total_sales": total_sales,
            "avg_order_value": round(avg_order, 2)
        }
    }


@router.get("/sales-by-category")
def get_sales_by_category(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("reports", "read"))
):
    """按商品分类统计销售额（SQL聚合，高效）"""
    start_date = datetime.now() - timedelta(days=days)

    # 用 PostgreSQL jsonb + LATERAL JOIN 展开 items 数组，左联 products 表获取真实分类
    sql = text("""
        SELECT
            COALESCE(p.category, 'other') AS category,
            SUM((item->>'quantity')::int) AS item_count,
            SUM((item->>'price')::float * (item->>'quantity')::int) AS sales
        FROM orders,
             json_array_elements(orders.items::json) AS item
        LEFT JOIN products p ON (item->>'productId')::int = p.id
        WHERE orders.status NOT IN ('cancelled', 'pending')
          AND orders.created_at >= :start_date
        GROUP BY COALESCE(p.category, 'other')
        ORDER BY sales DESC
        LIMIT :lim
    """)
    result = db.execute(sql, {"start_date": start_date, "lim": limit})
    rows = result.fetchall()

    total = sum(r.sales for r in rows)
    return {
        "days": days,
        "data": [
            {"category": r.category, "item_count": r.item_count, "sales": float(r.sales)}
            for r in rows
        ],
        "total": float(total)
    }


@router.get("/sales-comparison")
def get_sales_comparison(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("reports", "read"))
):
    """销售对比：本周vs上周、本月vs上月"""
    today = datetime.now().date()

    # 本周数据
    week_start = today - timedelta(days=today.weekday())
    week_start_dt = datetime.combine(week_start, datetime.min.time())
    week_end_dt = datetime.combine(today, datetime.max.time())

    # 上周数据
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start_dt - timedelta(seconds=1)

    # 本月数据
    month_start = today.replace(day=1)
    month_start_dt = datetime.combine(month_start, datetime.min.time())

    # 上月数据
    last_month_end = month_start_dt - timedelta(seconds=1)
    last_month_start = last_month_end.replace(day=1)

    def get_period_stats(start_dt, end_dt):
        orders_count = db.query(func.count(Order.id)).filter(
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
            Order.status.notin_(['cancelled', 'pending'])
        ).scalar()
        sales = db.query(func.sum(Order.total)).filter(
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
            Order.status.notin_(['cancelled', 'pending'])
        ).scalar() or 0
        return {"orders": orders_count, "sales": float(sales)}

    this_week = get_period_stats(week_start_dt, week_end_dt)
    last_week = get_period_stats(last_week_start, last_week_end)
    this_month = get_period_stats(month_start_dt, datetime.combine(today, datetime.max.time()))
    last_month = get_period_stats(last_month_start, last_month_end)

    def calc_change(current, previous):
        if previous == 0:
            return None
        return round(((current - previous) / previous) * 100, 1)

    return {
        "this_week": this_week,
        "last_week": last_week,
        "this_week_change": calc_change(this_week["sales"], last_week["sales"]),
        "this_month": this_month,
        "last_month": last_month,
        "this_month_change": calc_change(this_month["sales"], last_month["sales"]),
    }


@router.get("/top-products")
def get_top_products(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("reports", "read"))
):
    """热销商品排行（SQL聚合，高效）"""
    start_date = datetime.now() - timedelta(days=days)

    sql = text("""
        SELECT
            (item->>'productId')::int AS product_id,
            (item->>'name')::text AS product_name,
            SUM((item->>'quantity')::int) AS quantity,
            SUM((item->>'price')::float * (item->>'quantity')::int) AS sales
        FROM orders,
             json_array_elements(orders.items::json) AS item
        WHERE orders.status NOT IN ('cancelled', 'pending')
          AND orders.created_at >= :start_date
          AND (item->>'productId') IS NOT NULL
        GROUP BY (item->>'productId')::int, (item->>'name')::text
        ORDER BY sales DESC
        LIMIT :lim
    """)
    result = db.execute(sql, {"start_date": start_date, "lim": limit})
    rows = result.fetchall()

    return {
        "days": days,
        "data": [
            {
                "id": r.product_id,
                "name": r.product_name or "未知商品",
                "quantity": r.quantity,
                "sales": float(r.sales)
            }
            for r in rows
        ]
    }


@router.get("/customer-stats")
def get_customer_stats(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("reports", "read"))
):
    """客户统计（新客户、复购率等）"""
    today = datetime.now().date()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())

    # 本月新客户
    new_this_month = db.query(User).filter(
        User.created_at >= month_start
    ).count()

    # 本周新客户
    new_this_week = db.query(User).filter(
        User.created_at >= week_start
    ).count()

    # 总客户数
    total_customers = db.query(User).count()

    # 有过购买记录的客户（排除NULL）
    customers_with_orders = db.query(User.id).join(
        Order, User.id == Order.user_id
    ).filter(
        Order.status.notin_(['cancelled']),
        Order.user_id.isnot(None)
    ).distinct().count()

    # 复购率（有过2次以上购买的客户占比）
    repeat_customers = db.query(
        Order.user_id,
        func.count(Order.id).label('order_count')
    ).filter(
        Order.status.notin_(['cancelled']),
        Order.user_id.isnot(None)
    ).group_by(Order.user_id).having(
        func.count(Order.id) > 1
    ).count()

    repeat_rate = repeat_customers / customers_with_orders if customers_with_orders > 0 else 0

    return {
        "total_customers": total_customers,
        "new_this_month": new_this_month,
        "new_this_week": new_this_week,
        "customers_with_orders": customers_with_orders,
        "repeat_customers": repeat_customers,
        "repeat_rate": round(repeat_rate * 100, 1)  # 百分比
    }
