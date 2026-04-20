"""
花店后台管理系统 - FastAPI 后端
"""
import os
import mimetypes
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import engine, Base

# 修复 webp MIME 类型（FastAPI StaticFiles 默认不支持 webp）
mimetypes.add_type('image/webp', '.webp', True)
from routers import orders, products, users, appointments, stats, auth, contacts, i18n, coupons, users_auth, upload, reviews, reports, admin_logs, export, notifications, categories, shop, admin_users, email_verification

# 创建数据库表
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="🌸 花店后台管理系统 API",
    version="1.0.0",
    description="Flower Shop Admin Backend",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3458",
        "http://localhost:3457",
        "http://localhost:3000",
        "https://bkkflowers.com",
        "https://manguxianhua.com",
        "https://adminflowers.bkkflowers.com",
        "https://adminflowers.manguxianhua.com",
        "https://api.bkkflowers.com",
        "https://api.manguxianhua.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(stats.router, prefix="/api/stats", tags=["统计"])
app.include_router(orders.router, prefix="/api/orders", tags=["订单"])
app.include_router(products.router, prefix="/api/products", tags=["商品"])
app.include_router(users.router, prefix="/api/users", tags=["用户"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["预约"])
app.include_router(contacts.router, prefix="/api/contacts", tags=["联系"])
app.include_router(i18n.router, prefix="/api/i18n", tags=["多语言"])
app.include_router(coupons.router, prefix="/api/coupons", tags=["优惠券"])
app.include_router(users_auth.router, prefix="/api/user", tags=["用户"])
app.include_router(upload.router, prefix="/api/upload", tags=["上传"])
app.include_router(reviews.router, prefix="/api/reviews", tags=["评价"])
app.include_router(reports.router, prefix="/api/reports", tags=["报表"])
app.include_router(admin_logs.router, prefix="/api/admin-logs", tags=["日志"])
app.include_router(export.router, prefix="/api/export", tags=["导出"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["通知"])
app.include_router(categories.router, prefix="/api/categories", tags=["分类"])
app.include_router(shop.router, prefix="/api", tags=["店铺信息"])
app.include_router(admin_users.router, prefix="/api", tags=["店员管理"])
app.include_router(email_verification.router, prefix="/api/email", tags=["邮箱验证"])

# 静态文件服务（上传的图片）
os.makedirs("/app/static/uploads", exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory="/app/static/uploads"), name="uploads")


@app.get("/")
def root():
    return {"message": "🌸 Flower Shop Admin API", "version": "1.0.0"}


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
