from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user, oauth2_scheme
from ..budget_client import request_budget_check
from ..crud import create_expense, get_expense, get_owned_category, update_expense
from ..database import get_db
from ..models import Expense, User
from ..schemas import ExpenseCreate, ExpenseResponse, ExpenseUpdate

router = APIRouter(prefix="/expenses", tags=["expenses"])


def require_category(db: Session, category_id: int, user_id: int) -> None:
    if get_owned_category(db, category_id, user_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found for this user")


@router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def add_expense(
    data: ExpenseCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Expense:
    require_category(db, data.category_id, current_user.id)
    expense = create_expense(db, data, current_user.id)
    background_tasks.add_task(request_budget_check, token, expense.expense_date.month, expense.expense_date.year)
    return expense


@router.get("", response_model=list[ExpenseResponse])
def list_expenses(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Expense]:
    return list(db.scalars(select(Expense).where(Expense.user_id == current_user.id).order_by(Expense.expense_date.desc())))


@router.get("/{expense_id}", response_model=ExpenseResponse)
def read_expense(
    expense_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Expense:
    expense = get_expense(db, expense_id, current_user.id)
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return expense


@router.put("/{expense_id}", response_model=ExpenseResponse)
def edit_expense(
    expense_id: int,
    data: ExpenseUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Expense:
    expense = get_expense(db, expense_id, current_user.id)
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    if data.category_id is not None:
        require_category(db, data.category_id, current_user.id)
    updated = update_expense(db, expense, data)
    # Only the month the expense now belongs to needs checking: alerts fire when spending goes UP,
    # and moving an expense out of a month can only lower that month's total.
    background_tasks.add_task(request_budget_check, token, updated.expense_date.month, updated.expense_date.year)
    return updated


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_expense(
    expense_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    expense = get_expense(db, expense_id, current_user.id)
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    db.delete(expense)
    db.commit()