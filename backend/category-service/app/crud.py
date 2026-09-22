from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Category
from .schemas import CategoryCreate, CategoryUpdate

DEFAULT_CATEGORIES = (
    "Food",
    "Travel",
    "Shopping",
    "Bills",
    "Entertainment",
    "Healthcare",
    "Education",
    "Rent",
    "Other",
)


def list_categories(db: Session, user_id: int) -> list[Category]:
    categories = list(db.scalars(select(Category).where(Category.user_id == user_id).order_by(Category.name)))
    if categories:
        return categories
    categories = [Category(user_id=user_id, name=name) for name in DEFAULT_CATEGORIES]
    db.add_all(categories)
    db.commit()
    return list(db.scalars(select(Category).where(Category.user_id == user_id).order_by(Category.name)))


def get_category(db: Session, category_id: int, user_id: int) -> Category | None:
    return db.scalar(select(Category).where(Category.id == category_id, Category.user_id == user_id))


def create_category(db: Session, data: CategoryCreate, user_id: int) -> Category:
    category = Category(user_id=user_id, name=data.name.strip(), description=data.description)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def update_category(db: Session, category: Category, data: CategoryUpdate) -> Category:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(category, field, value.strip() if field == "name" and value else value)
    db.commit()
    db.refresh(category)
    return category