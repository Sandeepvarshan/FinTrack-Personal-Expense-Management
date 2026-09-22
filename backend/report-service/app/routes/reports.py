from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Expense, User
from ..schemas import BudgetVsActualReport, CategoryReport, MonthlyReport, ReportSummary, YearlyReport
from ..services.report_generator import budget_vs_actual, category_report, monthly

router = APIRouter(prefix="/reports", tags=["reports"])


def resolve_period(month: int | None, year: int | None) -> tuple[int, int]:
    """Fill in "this month / this year" when the caller did not pass one.

    This must run per request. Writing Query(default=date.today().month) would freeze the value
    at the moment the service started.
    """
    today = date.today()
    return month or today.month, year or today.year


@router.get("/monthly", response_model=MonthlyReport)
def monthly_report(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonthlyReport:
    month, year = resolve_period(month, year)
    return MonthlyReport.model_validate(monthly(db, current_user.id, month, year))


@router.get("/category", response_model=list[CategoryReport])
def categories_report(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CategoryReport]:
    return [CategoryReport.model_validate(item) for item in category_report(db, current_user.id, month, year)]


@router.get("/yearly", response_model=list[YearlyReport])
def yearly_report(
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[YearlyReport]:
    _, year = resolve_period(None, year)
    rows = db.execute(
        select(func.month(Expense.expense_date), func.coalesce(func.sum(Expense.amount), 0), func.count(Expense.id))
        .where(Expense.user_id == current_user.id, func.year(Expense.expense_date) == year)
        .group_by(func.month(Expense.expense_date)).order_by(func.month(Expense.expense_date))
    ).all()
    return [YearlyReport(month=row[0], total_expenses=row[1], transaction_count=row[2]) for row in rows]


@router.get("/budget-vs-actual", response_model=list[BudgetVsActualReport])
def budget_vs_actual_report(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    category_id: int | None = Query(default=None, gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BudgetVsActualReport]:
    month, year = resolve_period(month, year)
    return [
        BudgetVsActualReport.model_validate(item)
        for item in budget_vs_actual(db, current_user.id, month, year, category_id)
    ]


@router.get("/summary", response_model=ReportSummary)
def report_summary(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportSummary:
    month, year = resolve_period(month, year)
    current_month = monthly(db, current_user.id, month, year)
    total = db.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.user_id == current_user.id)) or 0
    count = db.scalar(select(func.count(Expense.id)).where(Expense.user_id == current_user.id)) or 0
    return ReportSummary(total_expenses=total, transaction_count=count, monthly=[MonthlyReport.model_validate(current_month)], categories=[CategoryReport.model_validate(item) for item in category_report(db, current_user.id, month, year)])