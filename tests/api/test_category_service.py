import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, text

SERVICE_PATH = Path(__file__).parents[2] / "backend" / "category-service"
package_spec = importlib.util.spec_from_file_location(
    "category_service_app",
    SERVICE_PATH / "app" / "__init__.py",
    submodule_search_locations=[str(SERVICE_PATH / "app")],
)
category_service_app = importlib.util.module_from_spec(package_spec)
sys.modules["category_service_app"] = category_service_app
package_spec.loader.exec_module(category_service_app)

from category_service_app.auth import get_current_user  # noqa: E402
from category_service_app.database import SessionLocal  # noqa: E402
from category_service_app.main import app  # noqa: E402
from category_service_app.models import Category  # noqa: E402
from category_service_app.config import settings  # noqa: E402
from jose import jwt  # noqa: E402

client = TestClient(app)


def create_user() -> tuple[int, str]:
    email = f"category-{uuid4().hex}@example.com"
    db = SessionLocal()
    try:
        result = db.execute(
            text("INSERT INTO users (name, email, password_hash) VALUES (:name, :email, :password_hash)"),
            {"name": "Category User", "email": email, "password_hash": "test-only"},
        )
        db.commit()
        user_id = result.lastrowid
        token = jwt.encode({"sub": str(user_id)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return user_id, token
    finally:
        db.close()


def cleanup(user_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Category).where(Category.user_id == user_id))
        db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
        db.commit()
    finally:
        db.close()


def test_category_defaults_crud_and_ownership():
    first_id, first_token = create_user()
    second_id, second_token = create_user()
    first_headers = {"Authorization": f"Bearer {first_token}"}
    second_headers = {"Authorization": f"Bearer {second_token}"}
    try:
        defaults = client.get("/categories", headers=first_headers)
        assert defaults.status_code == 200
        assert {category["name"] for category in defaults.json()} >= {"Food", "Rent", "Other"}

        created = client.post("/categories", headers=first_headers, json={"name": "Subscriptions"})
        assert created.status_code == 201
        category_id = created.json()["id"]
        assert client.get(f"/categories/{category_id}", headers=second_headers).status_code == 404
        assert client.put(f"/categories/{category_id}", headers=first_headers, json={"name": "Recurring"}).status_code == 200
        assert client.delete(f"/categories/{category_id}", headers=first_headers).status_code == 204
    finally:
        cleanup(first_id)
        cleanup(second_id)