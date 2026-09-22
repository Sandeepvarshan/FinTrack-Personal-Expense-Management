from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def blank_to_none(value: object) -> object:
    """HTML forms send "" for an empty <select>. For a budget that means "all categories"."""
    return None if value == "" else value


class BudgetCreate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    _blank_category = field_validator("category_id", mode="before")(blank_to_none)


class BudgetUpdate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    month: int | None = Field(default=None, ge=1, le=12)
    year: int | None = Field(default=None, ge=2000, le=2100)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)

    _blank_category = field_validator("category_id", mode="before")(blank_to_none)


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category_id: int | None
    month: int
    year: int
    amount: Decimal
    created_at: datetime


class AlertResult(BaseModel):
    budget_id: int
    status: str
    delivered: bool  # False if the Notification Service could not be reached


class BudgetUsage(BudgetResponse):
    spent: Decimal
    remaining: Decimal
    percentage_used: Decimal
    status: str