"""
初始化数据库和管理员账号
"""
import bcrypt
from models import Base, AdminUser, Product, Order, User, Appointment, Contact, Coupon
from database import engine, SessionLocal
from datetime import datetime, timedelta
import random

def init_db():
    # 创建表
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # 检查是否已有管理员
    existing_admin = db.query(AdminUser).filter(AdminUser.username == "admin").first()
    if not existing_admin:
        admin = AdminUser(
            username="admin",
            password_hash=bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            role="super_admin"
        )
        db.add(admin)
        # SECURITY NOTE: Default admin password is set here.
        # Change it immediately after first login via the admin panel.

    # 添加示例商品
    if db.query(Product).count() == 0:
        sample_products = [
            {
                "name": "浪漫玫瑰花束",
                "name_th": "ช่อกุหลาบโรแมนติก",
                "name_en": "Romantic Rose Bouquet",
                "description": "精选11朵红玫瑰，搭配满天星，象征一生一世的爱意",
                "description_th": "กุหลาบแดง 11 ดอก พร้อมแก้วเด็ด สื่อถึงความรักที่ยิ่งใหญ่",
                "description_en": "11 premium red roses with gypsophila, symbolizing eternal love",
                "price": 299,
                "original_price": 399,
                "images": ["https://images.unsplash.com/photo-1518882605630-8d53d2b2dc1b?w=600"],
                "stock": 50,
                "category": "rose",
                "tags": ["热卖", "新品"],
                "flower_count": 11
            },
            {
                "name": "粉色康乃馨",
                "name_th": "คาร์เนชั่นสีชมพู",
                "name_en": "Pink Carnation",
                "description": "温馨粉色康乃馨，适合送给母亲和长辈",
                "description_th": "คาร์เนชั่นสีชมพู อบอุ่น เหมาะสำหรับแม่และผู้ใหญ่",
                "description_en": "Warm pink carnations, perfect for mother and elders",
                "price": 199,
                "images": ["https://images.unsplash.com/photo-1420011912922-5f4d167898d0?w=600"],
                "stock": 30,
                "category": "bouquet",
                "tags": ["精选"],
                "flower_count": 11
            },
            {
                "name": "向日葵阳光花束",
                "name_th": "ช่อดอกทานตะวัน",
                "name_en": "Sunflower Bouquet",
                "description": "明亮向日葵，代表阳光和积极向上的生活态度",
                "description_th": "ดอกทานตะวันสดใส สื่อถึงแสงแดดและความหวัง",
                "description_en": "Bright sunflowers representing sunshine and positivity",
                "price": 259,
                "images": ["https://images.unsplash.com/photo-1597848212624-a19eb35e2651?w=600"],
                "stock": 25,
                "category": "bouquet",
                "tags": ["新品"],
                "flower_count": 11
            },
            {
                "name": "紫色薰衣草",
                "name_th": "ลาเวนเดอร์สีม่วง",
                "name_en": "Purple Lavender",
                "description": "浪漫紫色薰衣草，香气怡人，适合表白",
                "description_th": "ลาเวนเดอร์สีม่วงโรแมนติก หอมนุ่ม เหมาะสำหรับสารภาพรัก",
                "description_en": "Romantic purple lavender with pleasant fragrance, perfect for confession",
                "price": 329,
                "images": ["https://images.unsplash.com/photo-1499002238440-d264edd596ec?w=600"],
                "stock": 20,
                "category": "bouquet",
                "tags": ["热卖"],
                "flower_count": 11
            },
            {
                "name": "郁金香混搭",
                "name_th": "ทิวลิปผสม",
                "name_en": "Mixed Tulips",
                "description": "多彩郁金香，荷兰进口，品质优良",
                "description_th": "ทิวลิปหลากสี นำเข้าจากเนเธอร์แลนด์ คุณภาพดี",
                "description_en": "Colorful tulips imported from Netherlands",
                "price": 399,
                "original_price": 499,
                "images": ["https://images.unsplash.com/photo-1520763185298-1b434c919102?w=600"],
                "stock": 15,
                "category": "tulip",
                "tags": ["高端"],
                "flower_count": 11
            },
        ]

        for p in sample_products:
            product = Product(**p)
            db.add(product)
        print(f"✅ 已添加 {len(sample_products)} 个示例商品")

    # 添加示例用户
    if db.query(User).count() == 0:
        sample_users = [
            {"email": "john@example.com", "phone": "081-234-5678", "name": "John Smith"},
            {"email": "suda@example.com", "phone": "089-876-5432", "name": "สมชาย ใจดี"},
            {"email": "wang@example.com", "phone": "138-0013-8000", "name": "王小明"},
        ]
        for u in sample_users:
            user = User(**u)
            db.add(user)
        print(f"✅ 已添加 {len(sample_users)} 个示例用户")

    # 添加示例订单
    if db.query(Order).count() == 0:
        statuses = ["pending", "confirmed", "preparing", "shipped", "delivered"]
        for i in range(15):
            order = Order(
                order_no=f"FX{datetime.now().strftime('%Y%m%d')}{i+1:03d}",
                user_name=random.choice(["John Smith", "สมชาย", "王小明", "张三", "李四"]),
                total=random.choice([199, 299, 399, 499, 599]),
                status=random.choice(statuses),
                items=[{"productId": 1, "name": "浪漫玫瑰花束", "price": 299, "quantity": 1, "flowers": 11}],
                address="123 Sukhumvit Road, Bangkok",
                phone="081-234-5678",
                created_at=datetime.now() - timedelta(days=random.randint(0, 30))
            )
            db.add(order)
        print("✅ 已添加 15 个示例订单")

    # 添加示例预约
    if db.query(Appointment).count() == 0:
        occasions = ["proposal", "wedding", "birthday", "anniversary", "business"]
        for i in range(8):
            apt = Appointment(
                appointment_no=f"AP{datetime.now().strftime('%Y%m%d')}{i+1:03d}",
                customer_name=random.choice(["John Smith", "สมชาย", "王小明"]),
                customer_phone="081-234-5678",
                occasion=random.choice(occasions),
                budget=random.choice(["500-1000", "1000-2000", "2000-5000"]),
                delivery_date=(datetime.now() + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d"),
                recipient_name="收花人",
                recipient_phone="089-123-4567",
                delivery_address="456 Silom Road, Bangkok",
                requirements="请用粉色包装",
                status=random.choice(["pending", "confirmed", "in_progress"]),
                created_at=datetime.now() - timedelta(days=random.randint(0, 15))
            )
            db.add(apt)
        print("✅ 已添加 8 个示例预约")

    # 添加示例联系
    if db.query(Contact).count() == 0:
        for i in range(5):
            contact = Contact(
                name=random.choice(["张三", "李四", "สมชาย", "John"]),
                phone="081-234-5678",
                message=f"我想咨询一下花束配送的问题 {i+1}",
                status=random.choice(["pending", "replied"]),
                created_at=datetime.now() - timedelta(days=random.randint(0, 10))
            )
            db.add(contact)
        print("✅ 已添加 5 个示例联系记录")

    # 添加示例优惠券
    if db.query(Coupon).count() == 0:
        coupons = [
            {"code": "FLOWER10", "discount_type": "percent", "discount_value": 10, "min_amount": 100, "max_uses": 100, "used_count": 23},
            {"code": "SAVE20", "discount_type": "fixed", "discount_value": 20, "min_amount": 200, "max_uses": 50, "used_count": 15},
            {"code": "FIRST50", "discount_type": "fixed", "discount_value": 50, "min_amount": 300, "max_uses": 30, "used_count": 8},
            {"code": "VIP100", "discount_type": "fixed", "discount_value": 100, "min_amount": 500, "max_uses": 20, "used_count": 5},
        ]
        for c in coupons:
            coupon = Coupon(**c)
            db.add(coupon)
        print("✅ 已添加 4 个示例优惠券")

    # 添加示例配送员
    if db.query(DeliveryPerson).count() == 0:
        persons = [
            {"name": "张三", "phone": "089-111-2222", "avatar": "👨‍🎓", "status": "available"},
            {"name": "李四", "phone": "089-333-4444", "avatar": "👩‍🎓", "status": "busy"},
            {"name": "王五", "phone": "089-555-6666", "avatar": "👨‍💼", "status": "available"},
        ]
        for p in persons:
            person = DeliveryPerson(**p)
            db.add(person)
        print("✅ 已添加 3 个示例配送员")

    db.commit()
    db.close()
    print("\n🎉 数据库初始化完成!")
    print("=" * 50)
    print("📝 管理员账号: admin (密码请在部署后修改为强密码)")
    print("🌐 API文档: http://localhost:3457/docs")
    print("=" * 50)


if __name__ == "__main__":
    init_db()
