from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Category, Expense
from .schemas import ExpenseCreate, ExpenseUpdate


def get_expense(db: Session, expense_id: int, user_id: int) -> Expense | None:
    return db.scalar(select(Expense).where(Expense.id == expense_id, Expense.user_id == user_id))


def get_owned_category(db: Session, category_id: int, user_id: int) -> Category | None:
    return db.scalar(select(Category).where(Category.id == category_id, Category.user_id == user_id))


def create_expense(db: Session, data: ExpenseCreate, user_id: int) -> Expense:
    expense = Expense(user_id=user_id, **data.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def update_expense(db: Session, expense: Expense, data: ExpenseUpdate) -> Expense:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return expense