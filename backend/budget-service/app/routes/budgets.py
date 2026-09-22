from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alerts import evaluate_budgets, evaluate_in_background
from ..auth import get_current_user, oauth2_scheme
from ..crud import budget_exists, create_budget, get_budget, usage, validate_category, update_budget
from ..database import get_db
from ..models import Budget, User
from ..schemas import AlertResult, BudgetCreate, BudgetResponse, BudgetUpdate, BudgetUsage

router = APIRouter(prefix="/budgets", tags=["budgets"])


def category_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


def duplicate_error() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Budget already exists for this period")


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def add_budget(
    data: BudgetCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Budget:
    try:
        validate_category(db, data.category_id, current_user.id)
        if budget_exists(db, current_user.id, data.category_id, data.month, data.year):
            raise duplicate_error()
        budget = create_budget(db, data, current_user.id)
        # A new budget may already be at/over its limit (spending happened earlier this month).
        background_tasks.add_task(evaluate_in_background, current_user.id, token, budget.month, budget.year)
        return budget
    except ValueError as error:
        raise category_error(error)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Budget already exists for this period")


@router.post("/evaluate", response_model=list[AlertResult])
def evaluate(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Called by the Expense Service after spending changes: alert on any budget that is now at
    80% or over its limit. Only ever looks at the caller's own budgets."""
    return evaluate_budgets(db, current_user.id, token, month, year)


@router.get("", response_model=list[BudgetResponse])
def list_budgets(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Budget]:
    return list(db.scalars(select(Budget).where(Budget.user_id == current_user.id).order_by(Budget.year.desc(), Budget.month.desc())))


@router.get("/summary", response_model=list[BudgetUsage])
def budget_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[BudgetUsage]:
    budgets = list(db.scalars(select(Budget).where(Budget.user_id == current_user.id)))
    return [BudgetUsage.model_validate({**BudgetResponse.model_validate(budget).model_dump(), **usage(db, budget)}) for budget in budgets]


@router.get("/{budget_id}", response_model=BudgetUsage)
def read_budget(
    budget_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> BudgetUsage:
    budget = get_budget(db, budget_id, current_user.id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return BudgetUsage.model_validate({**BudgetResponse.model_validate(budget).model_dump(), **usage(db, budget)})


@router.put("/{budget_id}", response_model=BudgetResponse)
def edit_budget(
    budget_id: int,
    data: BudgetUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Budget:
    budget = get_budget(db, budget_id, current_user.id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    try:
        validate_category(db, data.category_id, current_user.id) if data.category_id is not None else None
        category_id = data.category_id if "category_id" in data.model_fields_set else budget.category_id
        month = data.month if data.month is not None else budget.month
        year = data.year if data.year is not None else budget.year
        if budget_exists(db, current_user.id, category_id, month, year, exclude_id=budget.id):
            raise duplicate_error()
        updated = update_budget(db, budget, data)
        background_tasks.add_task(evaluate_in_background, current_user.id, token, updated.month, updated.year)
        return updated
    except ValueError as error:
        raise category_error(error)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Budget already exists for this period")


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_budget(
    budget_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    budget = get_budget(db, budget_id, current_user.id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    db.delete(budget)
    db.commit()