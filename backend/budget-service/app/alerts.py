from sqlalchemy import select
from sqlalchemy.orm import Session

from .crud import WARNING_PERCENT, usage
from .database import SessionLocal
from .models import Budget, Category
from .notifier import send_notification

WARNING_TYPE = "budget_warning"
EXCEEDED_TYPE = "budget_exceeded"


def alert_text(status: str, label: str, month: int, year: int) -> tuple[str, str]:
    """(type, message). The message is deliberately free of amounts so that it is identical every
    time the same budget is evaluated - that is what lets the Notification Service de-duplicate."""
    period = f"{month:02d}/{year}"
    if status == "exceeded":
        return EXCEEDED_TYPE, f"Budget for {label} ({period}) has been exceeded"
    return WARNING_TYPE, f"Budget for {label} ({period}) has reached {WARNING_PERCENT}% of its limit"


def evaluate_budgets(
    db: Session, user_id: int, token: str, month: int | None = None, year: int | None = None
) -> list[dict[str, object]]:
    """Check the user's budgets (optionally only one month) and send an alert for each that is
    in 'warning' or 'exceeded' state. Returns one entry per budget that needed an alert."""
    query = select(Budget).where(Budget.user_id == user_id)
    if month is not None:
        query = query.where(Budget.month == month)
    if year is not None:
        query = query.where(Budget.year == year)

    results: list[dict[str, object]] = []
    for budget in list(db.scalars(query)):
        status = str(usage(db, budget)["status"])
        if status == "on_track":
            continue
        label = "all categories"
        if budget.category_id is not None:
            label = db.scalar(select(Category.name).where(Category.id == budget.category_id)) or label
        notification_type, message = alert_text(status, label, budget.month, budget.year)
        delivered = send_notification(token, notification_type, message)
        results.append({"budget_id": budget.id, "status": status, "delivered": delivered})
    return results


def evaluate_in_background(user_id: int, token: str, month: int, year: int) -> None:
    """Same as evaluate_budgets but opens its own DB session, for use after the response was sent."""
    db = SessionLocal()
    try:
        evaluate_budgets(db, user_id, token, month, year)
    finally:
        db.close()
