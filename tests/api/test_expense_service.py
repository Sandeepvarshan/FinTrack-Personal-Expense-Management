import sys
from datetime import date
import importlib.util
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, text

SERVICE_PATH = Path(__file__).parents[2] / "backend" / "expense-service"

package_spec = importlib.util.spec_from_file_location(
    "expense_service_app",
    SERVICE_PATH / "app" / "__init__.py",
    submodule_search_locations=[str(SERVICE_PATH / "app")],
)
expense_service_app = importlib.util.module_from_spec(package_spec)
sys.modules["expense_service_app"] = expense_service_app
package_spec.loader.exec_module(expense_service_app)

from expense_service_app.auth import create_access_token  # noqa: E402
from expense_service_app.database import SessionLocal  # noqa: E402
from expense_service_app.main import app  # noqa: E402
from expense_service_app.models import Category, Expense, User  # noqa: E402

client = TestClient(app)


def create_user(name: str) -> tuple[int, str]:
    email = f"expense-{uuid4().hex}@example.com"
    db = SessionLocal()
    try:
        user = User(name=name, email=email, password_hash="test-only")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, create_access_token(user.id)
    finally:
        db.close()


def create_category(user_id: int) -> int:
    db = SessionLocal()
    try:
        category = Category(user_id=user_id, name=f"Test {uuid4().hex[:8]}")
        db.add(category)
        db.commit()
        db.refresh(category)
        return category.id
    finally:
        db.close()


def cleanup(user_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        for user_id in user_ids:
            db.execute(delete(Expense).where(Expense.user_id == user_id))
            db.execute(delete(Category).where(Category.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))
        db.commit()
    finally:
        db.close()


def test_expense_crud_and_ownership():
    first_id, first_token = create_user("Expense Owner")
    second_id, second_token = create_user("Other Owner")
    category_id = create_category(first_id)
    headers = {"Authorization": f"Bearer {first_token}"}
    try:
        created = client.post(
            "/expenses",
            headers=headers,
            json={"category_id": category_id, "amount": "125.50", "description": "Groceries", "expense_date": str(date.today()), "payment_method": "Card"},
        )
        assert created.status_code == 201
        expense_id = created.json()["id"]
        assert client.get("/expenses", headers=headers).json()[0]["description"] == "Groceries"
        assert client.put(f"/expenses/{expense_id}", headers=headers, json={"amount": "140.00"}).status_code == 200
        assert client.get(f"/expenses/{expense_id}", headers={"Authorization": f"Bearer {second_token}"}).status_code == 404
        assert client.delete(f"/expenses/{expense_id}", headers=headers).status_code == 204
    finally:
        cleanup([first_id, second_id])