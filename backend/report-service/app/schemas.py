from decimal import Decimal

from pydantic import BaseModel


class MonthlyReport(BaseModel):
    month: int
    year: int
    total_expenses: Decimal
    transaction_count: int


class CategoryReport(BaseModel):
    category_id: int
    category_name: str
    total_amount: Decimal
    percentage: Decimal


class YearlyReport(BaseModel):
    month: int
    total_expenses: Decimal
    transaction_count: int


class ReportSummary(BaseModel):
    total_expenses: Decimal
    transaction_count: int
    monthly: list[MonthlyReport]
    categories: list[CategoryReport]


class BudgetVsActualReport(BaseModel):
    budget_id: int
    category_id: int | None
    category_name: str | None
    month: int
    year: int
    budget_amount: Decimal
    actual_amount: Decimal
    variance: Decimal
    percentage_used: Decimal
    status: str