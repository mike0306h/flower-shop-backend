"""
数据导出功能
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timedelta
import io
import csv
from database import get_db
from models import Order, Product, User, Coupon, Review
from auth import get_current_admin

router = APIRouter()


def generate_csv(headers, rows):
    """生成CSV文件"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        # 处理可能包含逗号或引号的字段
        cleaned_row = []
        for cell in row:
            if cell is None:
                cleaned_row.append('')
            elif isinstance(cell, (list, dict)):
                cleaned_row.append(str(cell))
            else:
                cleaned_row.append(str(cell))
        writer.writerow(cleaned_row)
    output.seek(0)
    return output


@router.get("/orders")
def export_orders(
    status: str = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """导出订单数据"""
    start_date = datetime.now() - timedelta(days=days)

    query = db.query(Order).filter(Order.created_at >= start_date)
    if status:
        query = query.filter(Order.status == status)

    orders = query.order_by(desc(Order.created_at)).all()

    headers = ['订单号', '客户姓名', '电话', '地址', '总价', '状态', '优惠券', '折扣', '配送时段', '备注', '下单时间']
    rows = []
    for o in orders:
        rows.append([
            o.order_no,
            o.user_name or '',
            o.phone or '',
            o.address or '',
            o.total,
            o.status,
            o.coupon_code or '',
            o.discount or 0,
            o.time_slot or '',
            o.note or '',
            o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else ''
        ])

    csv_output = generate_csv(headers, rows)

    return StreamingResponse(
        iter([csv_output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=orders-{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@router.get("/products")
def export_products(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """导出商品数据"""
    products = db.query(Product).order_by(Product.id).all()

    headers = ['ID', '名称', '名称(泰)', '名称(英)', '价格', '原价', '库存', '预警阈值', '分类', '标签', '状态', '创建时间']
    rows = []
    for p in products:
        rows.append([
            p.id,
            p.name or '',
            p.name_th or '',
            p.name_en or '',
            p.price,
            p.original_price or '',
            p.stock,
            p.stock_threshold,
            p.category or '',
            ','.join(p.tags) if p.tags else '',
            '启用' if p.active else '禁用',
            p.created_at.strftime('%Y-%m-%d %H:%M:%S') if p.created_at else ''
        ])

    csv_output = generate_csv(headers, rows)

    return StreamingResponse(
        iter([csv_output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=products-{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@router.get("/customers")
def export_customers(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """导出客户数据"""
    users = db.query(User).order_by(desc(User.created_at)).all()

    headers = ['ID', '姓名', '邮箱', '电话', 'LINE Token', '等级', '积分', '累计消费', '注册时间']
    rows = []
    for u in users:
        rows.append([
            u.id,
            u.name or '',
            u.email or '',
            u.phone or '',
            u.line_token or '',
            u.level or 'normal',
            u.points or 0,
            u.total_spent or 0,
            u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else ''
        ])

    csv_output = generate_csv(headers, rows)

    return StreamingResponse(
        iter([csv_output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=customers-{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@router.get("/coupons")
def export_coupons(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """导出优惠券数据"""
    coupons = db.query(Coupon).order_by(desc(Coupon.created_at)).all()

    headers = ['ID', '代码', '类型', '值', '最低消费', '使用次数', '限免次数', '有效期开始', '有效期结束', '状态', '创建时间']
    rows = []
    for c in coupons:
        rows.append([
            c.id,
            c.code or '',
            c.discount_type or '',
            c.discount_value or 0,
            c.min_purchase or 0,
            c.usage_count or 0,
            c.max_usage or 0,
            c.valid_from.strftime('%Y-%m-%d') if c.valid_from else '',
            c.valid_until.strftime('%Y-%m-%d') if c.valid_until else '',
            '启用' if c.active else '禁用',
            c.created_at.strftime('%Y-%m-%d %H:%M:%S') if c.created_at else ''
        ])

    csv_output = generate_csv(headers, rows)

    return StreamingResponse(
        iter([csv_output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=coupons-{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@router.get("/reviews")
def export_reviews(
    product_id: int = Query(None),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """导出评价数据"""
    query = db.query(Review)
    if product_id:
        query = query.filter(Review.product_id == product_id)

    reviews = query.order_by(desc(Review.created_at)).all()

    headers = ['ID', '商品ID', '商品名称', '用户ID', '用户名', '评分', '评价内容', '评价图片', '已购买验证', '状态', '评价时间']
    rows = []
    for r in reviews:
        product = db.query(Product).filter(Product.id == r.product_id).first()
        user = db.query(User).filter(User.id == r.user_id).first()

        rows.append([
            r.id,
            r.product_id,
            product.name if product else '',
            r.user_id,
            user.name if user else '',
            r.rating,
            r.comment or '',
            ','.join(r.images) if r.images else '',
            '是' if r.is_verified else '否',
            '显示' if r.active else '隐藏',
            r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else ''
        ])

    csv_output = generate_csv(headers, rows)

    return StreamingResponse(
        iter([csv_output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=reviews-{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@router.get("/backup")
def full_backup(
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    """导出完整备份（所有数据）"""
    if current_admin.get("role") != "admin":
        return {"error": "只有管理员可以执行完整备份"}

    # 获取所有数据
    orders = db.query(Order).order_by(Order.id).all()
    products = db.query(Product).order_by(Product.id).all()
    users = db.query(User).order_by(User.id).all()
    coupons = db.query(Coupon).order_by(Coupon.id).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # 写入订单数据
    writer.writerow(['=== 订单数据 ==='])
    writer.writerow(['订单号', '客户', '电话', '地址', '总价', '状态', '下单时间'])
    for o in orders:
        writer.writerow([
            o.order_no, o.user_name or '', o.phone or '', o.address or '',
            o.total, o.status,
            o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else ''
        ])

    writer.writerow([])  # 空行分隔

    # 写入商品数据
    writer.writerow(['=== 商品数据 ==='])
    writer.writerow(['ID', '名称', '价格', '库存', '分类', '状态'])
    for p in products:
        writer.writerow([p.id, p.name, p.price, p.stock, p.category, '启用' if p.active else '禁用'])

    writer.writerow([])

    # 写入客户数据
    writer.writerow(['=== 客户数据 ==='])
    writer.writerow(['ID', '姓名', '邮箱', '电话', '等级', '积分', '累计消费', '注册时间'])
    for u in users:
        writer.writerow([
            u.id, u.name or '', u.email or '', u.phone or '',
            u.level or 'normal', u.points or 0, u.total_spent or 0,
            u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else ''
        ])

    writer.writerow([])

    # 写入优惠券数据
    writer.writerow(['=== 优惠券数据 ==='])
    writer.writerow(['ID', '代码', '类型', '值', '使用次数', '限免', '有效期', '状态'])
    for c in coupons:
        writer.writerow([
            c.id, c.code or '', c.discount_type or '', c.discount_value or 0,
            c.usage_count or 0, c.max_usage or 0,
            c.valid_until.strftime('%Y-%m-%d') if c.valid_until else '',
            '启用' if c.active else '禁用'
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=full-backup-{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )
