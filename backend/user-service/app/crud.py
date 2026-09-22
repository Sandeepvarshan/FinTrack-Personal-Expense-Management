from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .models import User
from .schemas import UserCreate, UserUpdate


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def create_user(db: Session, user_data: UserCreate) -> User:
    user = User(
        name=user_data.name.strip(),
        email=str(user_data.email).lower(),
        password_hash=hash_password(user_data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, user_data: UserUpdate) -> User:
    changes = user_data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        user.name = changes["name"].strip()
    if "email" in changes and changes["email"] is not None:
        user.email = str(changes["email"]).lower()
    if "password" in changes and changes["password"] is not None:
        user.password_hash = hash_password(changes["password"])
    db.commit()
    db.refresh(user)
    return user