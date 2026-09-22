import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, text

SERVICE_PATH = Path(__file__).parents[2] / "backend" / "notification-service"
package_spec = importlib.util.spec_from_file_location("notification_service_app", SERVICE_PATH / "app" / "__init__.py", submodule_search_locations=[str(SERVICE_PATH / "app")])
notification_service_app = importlib.util.module_from_spec(package_spec)
sys.modules["notification_service_app"] = notification_service_app
package_spec.loader.exec_module(notification_service_app)

from notification_service_app.config import settings  # noqa: E402
from notification_service_app.database import SessionLocal  # noqa: E402
from notification_service_app.main import app  # noqa: E402
from notification_service_app.models import Notification  # noqa: E402
from jose import jwt  # noqa: E402

client = TestClient(app)


def create_user() -> tuple[int, str]:
    db = SessionLocal()
    try:
        user_id = db.execute(text("INSERT INTO users (name, email, password_hash) VALUES (:name, :email, :password_hash)"), {"name": "Notification User", "email": f"notification-{uuid4().hex}@example.com", "password_hash": "test-only"}).lastrowid
        db.commit()
        return user_id, jwt.encode({"sub": str(user_id)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    finally:
        db.close()


def cleanup(user_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Notification).where(Notification.user_id == user_id)); db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id}); db.commit()
    finally:
        db.close()


def test_notification_lifecycle_is_user_scoped():
    user_id, token = create_user()
    try:
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/notifications", headers=headers, json={"message": "Budget is 80% used", "type": "budget_warning"})
        assert created.status_code == 201
        notification_id = created.json()["id"]
        assert client.get("/notifications", headers=headers).json()[0]["is_read"] is False
        assert client.put(f"/notifications/{notification_id}/read", headers=headers).json()["is_read"] is True
        assert client.delete(f"/notifications/{notification_id}", headers=headers).status_code == 204
    finally:
        cleanup(user_id)

def test_creating_an_identical_notification_twice_returns_the_existing_one():
    user_id, token = create_user()
    other_id, other_token = create_user()
    try:
        headers = {"Authorization": f"Bearer {token}"}
        body = {"message": "Budget for Food (09/2026) has been exceeded", "type": "budget_exceeded"}
        first = client.post("/notifications", headers=headers, json=body)
        second = client.post("/notifications", headers=headers, json=body)
        assert (first.status_code, second.status_code) == (201, 200)
        assert first.json()["id"] == second.json()["id"]
        assert len(client.get("/notifications", headers=headers).json()) == 1
        # a different user with the same text still gets their own notification
        assert client.post("/notifications", headers={"Authorization": f"Bearer {other_token}"}, json=body).status_code == 201
    finally:
        cleanup(user_id)
        cleanup(other_id)


def test_another_users_notification_is_invisible_and_untouchable():
    owner_id, owner_token = create_user()
    intruder_id, intruder_token = create_user()
    try:
        created = client.post("/notifications", headers={"Authorization": f"Bearer {owner_token}"}, json={"message": "private", "type": "info"})
        notification_id = created.json()["id"]
        intruder = {"Authorization": f"Bearer {intruder_token}"}
        assert client.get(f"/notifications/{notification_id}", headers=intruder).status_code == 404
        assert client.put(f"/notifications/{notification_id}/read", headers=intruder).status_code == 404
        assert client.delete(f"/notifications/{notification_id}", headers=intruder).status_code == 404
        assert client.get("/notifications", headers=intruder).json() == []
    finally:
        cleanup(owner_id)
        cleanup(intruder_id)


def test_notifications_require_authentication():
    assert client.get("/notifications").status_code == 401
