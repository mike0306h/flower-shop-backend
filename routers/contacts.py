"""
联系管理
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from database import get_db
from models import Contact
from schemas import ContactUpdate, ContactResponse, ContactCreate
from auth import get_current_admin
from services.notification import send_contact_notification

router = APIRouter()


@router.get("", response_model=dict)
def get_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: str = "",
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    query = db.query(Contact)

    if status:
        query = query.filter(Contact.status == status)

    if search:
        query = query.filter(
            (Contact.name.contains(search)) |
            (Contact.phone.contains(search)) |
            (Contact.message.contains(search))
        )

    total = query.count()
    contacts = query.order_by(desc(Contact.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [ContactResponse.model_validate(c).model_dump() for c in contacts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.patch("/{contact_id}", response_model=dict)
def update_contact(
    contact_id: int,
    data: ContactUpdate,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)

    db.commit()
    db.refresh(contact)
    return ContactResponse.model_validate(contact).model_dump()


@router.delete("/{contact_id}")
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    db.delete(contact)
    db.commit()

    from .admin_logs import log_admin_action
    log_admin_action(db, admin_id=current_admin["id"], admin_name=current_admin.get("username","admin"), action="delete", target_type="contact", target_id=contact_id,            detail=json.dumps({"key": "log_contact_delete", "contact_id": contact_id}))

    return {"success": True}


# 前台提交联系表单（无需认证）
@router.post("/public", response_model=dict)
def submit_contact(
    request: ContactCreate,
    db: Session = Depends(get_db)
):
    contact = Contact(
        name=request.name,
        phone=request.phone,
        message=request.message,
        status="pending"
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)

    # 发送通知给管理员
    contact_dict = ContactResponse.model_validate(contact).model_dump()
    try:
        send_contact_notification(db, contact_dict)
    except Exception as e:
        pass  # 通知失败不影响主流程

    return {"success": True, "id": contact.id}
