from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Budget, Category, Expense
from .schemas import BudgetCreate, BudgetUpdate


WARNING_PERCENT = 80  # a budget at or above this share of its limit is 'warning'


def get_budget(db: Session, budget_id: int, user_id: int) -> Budget | None:
    return db.scalar(select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id))


def budget_exists(
    db: Session, user_id: int, category_id: int | None, month: int, year: int, exclude_id: int | None = None
) -> bool:
    """True if this user already has a budget for the same category (or 'all') in the same month.

    The database UNIQUE key covers (user, category, month, year), but MySQL never treats two NULLs as
    equal, so 'all categories' budgets would slip through. We check explicitly.
    """
    query = select(Budget.id).where(
        Budget.user_id == user_id,
        Budget.month == month,
        Budget.year == year,
        Budget.category_id.is_(None) if category_id is None else Budget.category_id == category_id,
    )
    if exclude_id is not None:
        query = query.where(Budget.id != exclude_id)
    return db.scalar(query.limit(1)) is not None


def validate_category(db: Session, category_id: int | None, user_id: int) -> None:
    if category_id is not None and db.scalar(select(Category.id).where(Category.id == category_id, Category.user_id == user_id)) is None:
        raise ValueError("Category not found for this user")


def calculate_spent(db: Session, budget: Budget) -> Decimal:
    query = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == budget.user_id,
        func.month(Expense.expense_date) == budget.month,
        func.year(Expense.expense_date) == budget.year,
    )
    if budget.category_id is not None:
        query = query.where(Expense.category_id == budget.category_id)
    return Decimal(str(db.scalar(query) or 0))


def usage(db: Session, budget: Budget) -> dict[str, object]:
    spent = calculate_spent(db, budget)
    remaining = budget.amount - spent
    percentage = (spent / budget.amount * 100).quantize(Decimal("0.01"))
    status = "exceeded" if spent > budget.amount else "warning" if percentage >= WARNING_PERCENT else "on_track"
    return {"spent": spent, "remaining": remaining, "percentage_used": percentage, "status": status}


def create_budget(db: Session, data: BudgetCreate, user_id: int) -> Budget:
    budget = Budget(user_id=user_id, **data.model_dump())
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def update_budget(db: Session, budget: Budget, data: BudgetUpdate) -> Budget:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(budget, field, value)
    db.commit()
    db.refresh(budget)
    return budget