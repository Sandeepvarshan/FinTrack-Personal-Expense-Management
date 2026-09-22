from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Budget, Category, Expense


def monthly(db: Session, user_id: int, month: int, year: int) -> dict[str, object]:
    total, count = db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0), func.count(Expense.id)).where(
            Expense.user_id == user_id,
            func.month(Expense.expense_date) == month,
            func.year(Expense.expense_date) == year,
        )
    ).one()
    return {"month": month, "year": year, "total_expenses": Decimal(str(total or 0)), "transaction_count": count}


def category_report(db: Session, user_id: int, month: int | None, year: int | None) -> list[dict[str, object]]:
    query = select(Category.id, Category.name, func.coalesce(func.sum(Expense.amount), 0)).join(
        Expense, Expense.category_id == Category.id
    ).where(Category.user_id == user_id, Expense.user_id == user_id).group_by(Category.id, Category.name)
    if month is not None:
        query = query.where(func.month(Expense.expense_date) == month)
    if year is not None:
        query = query.where(func.year(Expense.expense_date) == year)
    rows = db.execute(query).all()
    total = sum((Decimal(str(row[2])) for row in rows), Decimal("0"))
    return [
        {"category_id": row[0], "category_name": row[1], "total_amount": Decimal(str(row[2])), "percentage": (Decimal(str(row[2])) / total * 100).quantize(Decimal("0.01")) if total else Decimal("0")}
        for row in rows
    ]


def budget_vs_actual(
    db: Session, user_id: int, month: int, year: int, category_id: int | None = None
) -> list[dict[str, object]]:
    query = select(Budget, Category.name).outerjoin(Category, Category.id == Budget.category_id).where(
        Budget.user_id == user_id, Budget.month == month, Budget.year == year
    )
    if category_id is not None:
        query = query.where(Budget.category_id == category_id)

    reports = []
    for budget, category_name in db.execute(query).all():
        actual_query = select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.user_id == user_id,
            func.month(Expense.expense_date) == month,
            func.year(Expense.expense_date) == year,
        )
        if budget.category_id is not None:
            actual_query = actual_query.where(Expense.category_id == budget.category_id)
        actual = Decimal(str(db.scalar(actual_query) or 0))
        percentage = (actual / budget.amount * 100).quantize(Decimal("0.01"))
        reports.append(
            {
                "budget_id": budget.id,
                "category_id": budget.category_id,
                "category_name": category_name,
                "month": month,
                "year": year,
                "budget_amount": budget.amount,
                "actual_amount": actual,
                "variance": actual - budget.amount,
                "percentage_used": percentage,
                "status": "exceeded" if actual > budget.amount else "warning" if percentage >= 80 else "on_track",
            }
        )
    return reports