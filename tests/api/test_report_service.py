import importlib.util
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, text

SERVICE_PATH = Path(__file__).parents[2] / "backend" / "report-service"
package_spec = importlib.util.spec_from_file_location("report_service_app", SERVICE_PATH / "app" / "__init__.py", submodule_search_locations=[str(SERVICE_PATH / "app")])
report_service_app = importlib.util.module_from_spec(package_spec)
sys.modules["report_service_app"] = report_service_app
package_spec.loader.exec_module(report_service_app)

from report_service_app.config import settings  # noqa: E402
from report_service_app.database import SessionLocal  # noqa: E402
from report_service_app.main import app  # noqa: E402
from report_service_app.models import Budget, Category, Expense  # noqa: E402
from jose import jwt  # noqa: E402

client = TestClient(app)


def setup_data() -> tuple[int, str]:
    db = SessionLocal()
    try:
        user_id = db.execute(text("INSERT INTO users (name, email, password_hash) VALUES (:name, :email, :password_hash)"), {"name": "Report User", "email": f"report-{uuid4().hex}@example.com", "password_hash": "test-only"}).lastrowid
        category_id = db.execute(text("INSERT INTO categories (user_id, name) VALUES (:user_id, :name)"), {"user_id": user_id, "name": f"Report Category {uuid4().hex[:8]}"}).lastrowid
        db.execute(text("INSERT INTO expenses (user_id, category_id, amount, description, expense_date, payment_method) VALUES (:user_id, :category_id, :amount, :description, :expense_date, :payment_method)"), {"user_id": user_id, "category_id": category_id, "amount": "250.00", "description": "Report spend", "expense_date": date.today(), "payment_method": "Card"})
        db.commit()
        return user_id, jwt.encode({"sub": str(user_id)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    finally:
        db.close()


def cleanup(user_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Budget).where(Budget.user_id == user_id)); db.execute(delete(Expense).where(Expense.user_id == user_id)); db.execute(delete(Category).where(Category.user_id == user_id)); db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id}); db.commit()
    finally:
        db.close()


def test_reports_are_aggregated_per_user():
    user_id, token = setup_data()
    try:
        headers = {"Authorization": f"Bearer {token}"}
        monthly = client.get(f"/reports/monthly?month={date.today().month}&year={date.today().year}", headers=headers)
        assert monthly.status_code == 200
        assert float(monthly.json()["total_expenses"]) == 250
        categories = client.get("/reports/category", headers=headers)
        assert categories.status_code == 200
        assert float(categories.json()[0]["total_amount"]) == 250
    finally:
        cleanup(user_id)

def test_default_period_is_resolved_per_request_not_at_service_startup(monkeypatch):
    """Regression: defaults like Query(default=date.today().month) are evaluated ONCE at import,
    so a long-running service would keep serving the month it was started in."""
    import report_service_app.routes.reports as reports_module

    class FakeDate(date):
        @classmethod
        def today(cls):
            return date(2031, 8, 15)

    monkeypatch.setattr(reports_module, "date", FakeDate)
    user_id, token = setup_data()  # creates the user + category + a "today" expense (not in Aug 2031)
    try:
        db = SessionLocal()
        try:
            category_id = db.execute(text("SELECT id FROM categories WHERE user_id = :u"), {"u": user_id}).scalar()
            db.execute(
                text("INSERT INTO expenses (user_id, category_id, amount, description, expense_date, payment_method) VALUES (:u, :c, 40.00, 'aug', '2031-08-10', 'Card')"),
                {"u": user_id, "c": category_id},
            )
            db.commit()
        finally:
            db.close()
        headers = {"Authorization": f"Bearer {token}"}
        monthly = client.get("/reports/monthly", headers=headers).json()
        assert (monthly["month"], monthly["year"]) == (8, 2031)
        assert float(monthly["total_expenses"]) == 40
        yearly = client.get("/reports/yearly", headers=headers).json()
        assert [row["month"] for row in yearly] == [8]
        summary = client.get("/reports/summary", headers=headers).json()
        assert summary["monthly"][0]["month"] == 8
    finally:
        cleanup(user_id)


def test_reports_never_include_another_users_spending():
    owner_id, _ = setup_data()
    other_id, other_token = setup_data()
    try:
        # both users have exactly one 250.00 expense today; nobody may see the sum of both
        summary = client.get("/reports/summary", headers={"Authorization": f"Bearer {other_token}"}).json()
        assert float(summary["total_expenses"]) == 250
        assert summary["transaction_count"] == 1
    finally:
        cleanup(owner_id)
        cleanup(other_id)


def test_reports_require_authentication():
    for path in ("/reports/monthly", "/reports/category", "/reports/yearly", "/reports/summary", "/reports/budget-vs-actual"):
        assert client.get(path).status_code == 401


def test_budget_vs_actual_report_matches_budget_scope_and_user():
    user_id, token = setup_data()
    other_id, _ = setup_data()
    headers = {"Authorization": f"Bearer {token}"}
    db = SessionLocal()
    try:
        category_id = db.execute(text("SELECT id FROM categories WHERE user_id = :u"), {"u": user_id}).scalar()
        db.execute(
            text("INSERT INTO budgets (user_id, category_id, month, year, amount) VALUES (:u, :c, :m, :y, :a)"),
            {"u": user_id, "c": category_id, "m": date.today().month, "y": date.today().year, "a": "300.00"},
        )
        other_category_id = db.execute(text("SELECT id FROM categories WHERE user_id = :u"), {"u": other_id}).scalar()
        db.execute(
            text("INSERT INTO expenses (user_id, category_id, amount, description, expense_date, payment_method) VALUES (:u, :c, 50.00, 'other user', :d, 'Card')"),
            {"u": other_id, "c": other_category_id, "d": date.today()},
        )
        db.commit()
    finally:
        db.close()
    try:
        response = client.get(
            f"/reports/budget-vs-actual?month={date.today().month}&year={date.today().year}", headers=headers
        )
        assert response.status_code == 200
        report = response.json()[0]
        assert report["category_id"] == category_id
        assert float(report["budget_amount"]) == 300
        assert float(report["actual_amount"]) == 250
        assert float(report["variance"]) == -50
        assert report["status"] == "warning"
    finally:
        cleanup(user_id)
        cleanup(other_id)
