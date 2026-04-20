"""
飞鹅云打印机服务 (Feieyun)
文档: https://help.feieyun.com/home/doc/zh
使用标准库 urllib，无需安装第三方依赖
"""
import hashlib
import time
import urllib.request
import urllib.parse
import json
from datetime import datetime
from typing import Optional

FEIEYUN_URL = "https://api.feieyun.cn/Api/Open/printMsg"


def _make_sig(user: str, ukey: str) -> tuple[str, str]:
    """生成签名: SHA1(user + UKEY + stime)，返回 (sig, stime)"""
    stime = str(int(time.time()))
    sig = hashlib.sha1(f"{user}{ukey}{stime}".encode()).hexdigest()
    return sig, stime


def _build_receipt_text(order: dict, items: list, lang: str = "th") -> str:
    """
    构建小票文本内容（飞鹅标签格式）
    排版标签: <CB>居中放大 <B>放大 <C>居中 <BR>换行 <CUT>切刀
    """
    LABELS = {
        "th": {
            "shop": "Flower Shop",
            "order_no": "เลขที่ Order",
            "date": "วันที่ Date",
            "customer": "ลูกค้า Customer",
            "tel": "โทร Tel",
            "time_slot": "เวลาจัดส่ง",
            "address": "ที่อยู่",
            "items": "รายการ",
            "price": "ราคา",
            "discount": "ส่วนลด",
            "total": "รวม Total",
            "note": "หมายเหตุ",
            "thank": "ขอบคุณที่ใช้บริการค่ะ",
            "qty": "x",
        },
        "zh": {
            "shop": "鲜花小店",
            "order_no": "订单号",
            "date": "日期",
            "customer": "客户",
            "tel": "电话",
            "time_slot": "配送时段",
            "address": "地址",
            "items": "商品",
            "price": "价格",
            "discount": "折扣",
            "total": "合计",
            "note": "备注",
            "thank": "谢谢惠顾",
            "qty": "x",
        },
        "en": {
            "shop": "Flower Shop",
            "order_no": "Order No",
            "date": "Date",
            "customer": "Customer",
            "tel": "Tel",
            "time_slot": "Time Slot",
            "address": "Address",
            "items": "Items",
            "price": "Price",
            "discount": "Discount",
            "total": "Total",
            "note": "Note",
            "thank": "Thank you!",
            "qty": "x",
        },
    }
    lbl = LABELS.get(lang, LABELS["th"])

    date_str = order.get("created_at", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    lines = []
    lines.append(f"<CB>{lbl['shop']}</CB>")
    lines.append("<BR>")
    lines.append(f"{lbl['order_no']}: {order.get('order_no', '')}")
    lines.append(f"{lbl['date']}: {date_str}")
    lines.append(f"{lbl['customer']}: {order.get('user_name', '-')}")
    lines.append(f"{lbl['tel']}: {order.get('phone', '-')}")
    if order.get("time_slot"):
        lines.append(f"{lbl['time_slot']}: {order.get('time_slot')}")
    addr = order.get("address", "-")
    if len(addr) > 32:
        lines.append(f"{lbl['address']}:")
        lines.append(f"  {addr}")
    else:
        lines.append(f"{lbl['address']}: {addr}")
    lines.append("-" * 32)
    lines.append(f"{lbl['items']:<20}{lbl['price']:>12}")

    total = 0.0
    for item in items:
        name = item.get("name", "-")
        qty = item.get("quantity", 1)
        price = float(item.get("price", 0))
        total += price * qty
        item_str = f"{qty} x {name}"
        if len(item_str) > 20:
            name_line = name[:18] + ".."
        else:
            name_line = item_str
        price_str = f"฿{price:,.0f}"
        lines.append(f"{name_line:<20}{price_str:>12}")

    lines.append("-" * 32)
    discount = float(order.get("discount_amount", 0) or 0)
    if discount > 0:
        lines.append(f"{lbl['discount']}: -฿{discount:,.0f}")
    final_total = total - discount
    lines.append(f"{lbl['total']}: ฿{final_total:,.0f}")

    if order.get("note"):
        lines.append("<BR>")
        lines.append(f"{lbl['note']}: {order.get('note')}")

    lines.append("<BR>")
    lines.append(f"<C>{lbl['thank']}</C>")
    lines.append("<CUT>")

    return "\n".join(lines)


def _post_urlencoded(url: str, data: dict, timeout: int = 15) -> dict:
    """POST x-www-form-urlencoded，返回解析后的 JSON 响应"""
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_order(
    user: str,
    ukey: str,
    sn: str,
    order: dict,
    items: list,
    times: int = 1,
    lang: str = "th",
) -> dict:
    """
    打印小票到飞鹅云打印机
    返回: {"success": bool, "msg": str, "order_id": str or None}
    """
    if not user or not ukey or not sn:
        return {"success": False, "msg": "打印机未配置", "order_id": None}

    sig, stime = _make_sig(user, ukey)
    content = _build_receipt_text(order, items, lang)
    expired = str(int(time.time()) + 1800)

    payload = {
        "user": user,
        "stime": stime,
        "sig": sig,
        "apiname": "Open_printMsg",
        "sn": sn,
        "content": content,
        "times": str(times),
        "expired": expired,
    }

    try:
        result = _post_urlencoded(FEIEYUN_URL, payload)
        if result.get("ret") == 0:
            return {"success": True, "msg": "打印成功", "order_id": result.get("data")}
        else:
            return {"success": False, "msg": result.get("msg", "打印失败"), "order_id": None}
    except Exception as e:
        err_msg = str(e)
        if "timed out" in err_msg.lower():
            return {"success": False, "msg": "打印请求超时", "order_id": None}
        return {"success": False, "msg": f"打印异常: {err_msg}", "order_id": None}


def test_print(user: str, ukey: str, sn: str, lang: str = "th") -> dict:
    """打印测试页"""
    test_order = {
        "order_no": "TEST001",
        "created_at": datetime.now().isoformat(),
        "user_name": "测试客户 / ลูกค้าทดสอบ",
        "phone": "081-234-5678",
        "time_slot": "09:00-12:00",
        "address": "测试地址 / ที่อยู่ทดสอบ 123/4 ถนนสุขุมวิท กรุงเทพฯ 10160",
        "note": "测试备注 / หมายเหตุทดสอบ",
        "discount_amount": 0,
    }
    test_items = [
        {"name": "Bouquet (ช่อดอกไม้)", "quantity": 1, "price": 599},
        {"name": "Rose Bouquet (ช่อกุหลาบ)", "quantity": 2, "price": 299},
    ]
    return print_order(user, ukey, sn, test_order, test_items, times=1, lang=lang)
