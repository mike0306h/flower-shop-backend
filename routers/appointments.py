"""
预约路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from database import get_db
from models import Appointment
from schemas import AppointmentCreate, AppointmentUpdate, AppointmentResponse
from auth import get_current_admin, require_permission
from datetime import datetime
from services.notification import send_appointment_notification

router = APIRouter()


def generate_appointment_no():
    return f"AP{datetime.now().strftime('%Y%m%d')}{datetime.now().strftime('%H%M%S')}"


@router.post("/public", response_model=AppointmentResponse)
def create_appointment_public(
    data: AppointmentCreate,
    db: Session = Depends(get_db)
):
    """公开创建预约（无需认证）"""
    appointment = Appointment(
        appointment_no=generate_appointment_no(),
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        occasion=data.occasion,
        budget=data.budget,
        delivery_date=data.delivery_date,
        delivery_time=data.delivery_time,
        recipient_name=data.recipient_name,
        recipient_phone=data.recipient_phone,
        delivery_address=data.delivery_address,
        reference_images=data.reference_images or [],
        requirements=data.requirements,
        blessing_card=data.blessing_card,
        packaging=data.packaging,
        callback_time=data.callback_time,
        status="pending"
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    # 发送通知给管理员
    appointment_dict = AppointmentResponse.model_validate(appointment).model_dump()
    try:
        send_appointment_notification(db, appointment_dict)
    except Exception as e:
        pass  # 通知失败不影响主流程

    return appointment


@router.get("")
def get_appointments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    query = db.query(Appointment)

    if status:
        query = query.filter(Appointment.status == status)

    if search:
        query = query.filter(
            (Appointment.appointment_no.contains(search)) |
            (Appointment.customer_name.contains(search)) |
            (Appointment.customer_phone.contains(search))
        )

    total = query.count()
    appointments = query.order_by(desc(Appointment.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [AppointmentResponse.model_validate(a).model_dump() for a in appointments],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.get("/{appointment_id}")
def get_appointment(appointment_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="预约不存在")
    return AppointmentResponse.model_validate(appointment).model_dump()


@router.patch("/{appointment_id}")
def update_appointment(
    appointment_id: int,
    update_data: AppointmentUpdate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(require_permission("appointments", "update"))
):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="预约不存在")

    if update_data.status:
        appointment.status = update_data.status
    if update_data.note is not None:
        appointment.note = update_data.note
    if update_data.packaging is not None:
        appointment.packaging = update_data.packaging
    if update_data.callback_time is not None:
        appointment.callback_time = update_data.callback_time
    if update_data.reference_images is not None:
        appointment.reference_images = update_data.reference_images

    db.commit()
    db.refresh(appointment)
    return AppointmentResponse.model_validate(appointment).model_dump()


@router.delete("/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(require_permission("appointments", "delete"))):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="预约不存在")

    db.delete(appointment)
    db.commit()
    return {"message": "预约已删除"}
