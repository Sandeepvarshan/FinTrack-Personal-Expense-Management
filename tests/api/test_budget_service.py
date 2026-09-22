import importlib.util
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, text

SERVICE_PATH = Path(__file__).parents[2] / "backend" / "budget-service"
package_spec = importlib.util.spec_from_file_location(
    "budget_service_app",
    SERVICE_PATH / "app" / "__init__.py",
    submodule_search_locations=[str(SERVICE_PATH / "app")],
)
budget_service_app = importlib.util.module_from_spec(package_spec)
sys.modules["budget_service_app"] = budget_service_app
package_spec.loader.exec_module(budget_service_app)

from budget_service_app.config import settings  # noqa: E402
from budget_service_app.database import SessionLocal  # noqa: E402
from budget_service_app.main import app  # noqa: E402
from budget_service_app.models import Budget, Category, Expense  # noqa: E402
from jose import jwt  # noqa: E402

client = TestClient(app)


def create_user() -> tuple[int, str, int]:
    db = SessionLocal()
    try:
        user_result = db.execute(
            text("INSERT INTO users (name, email, password_hash) VALUES (:name, :email, :password_hash)"),
            {"name": "Budget User", "email": f"budget-{uuid4().hex}@example.com", "password_hash": "test-only"},
        )
        user_id = user_result.lastrowid
        category_result = db.execute(
            text("INSERT INTO categories (user_id, name) VALUES (:user_id, :name)"),
            {"user_id": user_id, "name": f"Budget Category {uuid4().hex[:8]}"},
        )
        db.commit()
        category_id = category_result.lastrowid
        token = jwt.encode({"sub": str(user_id)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return user_id, token, category_id
    finally:
        db.close()


def cleanup(user_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Budget).where(Budget.user_id == user_id))
        db.execute(delete(Expense).where(Expense.user_id == user_id))
        db.execute(delete(Category).where(Category.user_id == user_id))
        db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
        db.commit()
    finally:
        db.close()


def test_budget_usage_and_ownership():
    user_id, token, category_id = create_user()
    headers = {"Authorization": f"Bearer {token}"}
    db = SessionLocal()
    try:
        db.execute(
            text("INSERT INTO expenses (user_id, category_id, amount, description, expense_date, payment_method) VALUES (:user_id, :category_id, :amount, :description, :expense_date, :payment_method)"),
            {"user_id": user_id, "category_id": category_id, "amount": "6500.00", "description": "Test spend", "expense_date": date.today().replace(day=1), "payment_method": "Card"},
        )
        db.commit()
    finally:
        db.close()
    try:
        created = client.post("/budgets", headers=headers, json={"category_id": category_id, "month": date.today().month, "year": date.today().year, "amount": "8000.00"})
        assert created.status_code == 201
        budget_id = created.json()["id"]
        usage = client.get(f"/budgets/{budget_id}", headers=headers)
        assert usage.status_code == 200
        assert float(usage.json()["spent"]) == 6500
        assert float(usage.json()["remaining"]) == 1500
        assert float(usage.json()["percentage_used"]) == 81.25
        assert usage.json()["status"] == "warning"
        assert client.delete(f"/budgets/{budget_id}", headers=headers).status_code == 204
    finally:
        cleanup(user_id)

def test_blank_category_means_all_categories_budget():
    """The UI sends category_id="" for 'All categories'. That must create an overall budget, not a 422."""
    user_id, token, _ = create_user()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        created = client.post("/budgets", headers=headers, json={"category_id": "", "month": 1, "year": 2031, "amount": "5000"})
        assert created.status_code == 201
        assert created.json()["category_id"] is None
    finally:
        cleanup(user_id)


def test_duplicate_budget_for_same_scope_and_period_is_rejected():
    """MySQL UNIQUE indexes treat NULLs as distinct, so 'overall' budgets need an explicit check."""
    user_id, token, category_id = create_user()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        overall = {"category_id": None, "month": 2, "year": 2031, "amount": "5000"}
        assert client.post("/budgets", headers=headers, json=overall).status_code == 201
        assert client.post("/budgets", headers=headers, json={**overall, "amount": "9000"}).status_code == 409

        per_category = {"category_id": category_id, "month": 2, "year": 2031, "amount": "100"}
        assert client.post("/budgets", headers=headers, json=per_category).status_code == 201
        assert client.post("/budgets", headers=headers, json=per_category).status_code == 409

        # a different month is fine
        assert client.post("/budgets", headers=headers, json={**overall, "month": 3}).status_code == 201
    finally:
        cleanup(user_id)


def test_update_cannot_collide_with_another_budget():
    user_id, token, _ = create_user()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        first = client.post("/budgets", headers=headers, json={"category_id": None, "month": 4, "year": 2031, "amount": "100"}).json()
        second = client.post("/budgets", headers=headers, json={"category_id": None, "month": 5, "year": 2031, "amount": "100"}).json()
        collide = client.put(f"/budgets/{second['id']}", headers=headers, json={"month": 4})
        assert collide.status_code == 409
        # updating a budget without changing its scope/period must still work (it must not collide with itself)
        assert client.put(f"/budgets/{first['id']}", headers=headers, json={"amount": "250"}).status_code == 200
    finally:
        cleanup(user_id)


def test_user_cannot_read_change_or_delete_another_users_budget():
    owner_id, owner_token, _ = create_user()
    intruder_id, intruder_token, _ = create_user()
    owner = {"Authorization": f"Bearer {owner_token}"}
    intruder = {"Authorization": f"Bearer {intruder_token}"}
    try:
        budget_id = client.post("/budgets", headers=owner, json={"category_id": None, "month": 6, "year": 2031, "amount": "100"}).json()["id"]
        assert client.get(f"/budgets/{budget_id}", headers=intruder).status_code == 404
        assert client.put(f"/budgets/{budget_id}", headers=intruder, json={"amount": "1"}).status_code == 404
        assert client.delete(f"/budgets/{budget_id}", headers=intruder).status_code == 404
        assert budget_id not in [b["id"] for b in client.get("/budgets", headers=intruder).json()]
    finally:
        cleanup(owner_id)
        cleanup(intruder_id)


def test_cannot_budget_against_another_users_category():
    owner_id, _, owner_category = create_user()
    other_id, other_token, _ = create_user()
    try:
        response = client.post(
            "/budgets",
            headers={"Authorization": f"Bearer {other_token}"},
            json={"category_id": owner_category, "month": 7, "year": 2031, "amount": "100"},
        )
        assert response.status_code == 400
    finally:
        cleanup(owner_id)
        cleanup(other_id)


def test_budget_requires_authentication():
    assert client.get("/budgets").status_code == 401
