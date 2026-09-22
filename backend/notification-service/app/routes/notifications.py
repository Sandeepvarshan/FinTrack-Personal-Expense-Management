from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Notification, User
from ..schemas import NotificationCreate, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
def create_notification(
    data: NotificationCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Notification:
    """Create a notification. Idempotent: an identical one (same user, type, message) is returned
    with 200 instead of creating a duplicate, so the Budget Service can safely re-send an alert."""
    existing = db.scalar(
        select(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.type == data.type,
            Notification.message == data.message,
        )
        .limit(1)
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing
    notification = Notification(user_id=current_user.id, **data.model_dump())
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Notification]:
    return list(db.scalars(select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.created_at.desc())))


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_notification(
    notification_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Notification:
    notification = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id))
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.put("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Notification:
    notification = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id))
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    notification = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id))
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    db.delete(notification)
    db.commit()