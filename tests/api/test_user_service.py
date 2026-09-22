import sys
from uuid import uuid4
from pathlib import Path

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import delete

SERVICE_PATH = Path(__file__).parents[2] / "backend" / "user-service"
sys.path.insert(0, str(SERVICE_PATH))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

client = TestClient(app)


def make_test_email() -> str:
    return f"test-{uuid4().hex}@example.com"


def remove_user(user_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.id == user_id))
        db.commit()
    finally:
        db.close()


def test_register_login_and_profile():
    email = make_test_email()
    registration = client.post(
        "/users/register",
        json={"name": "Asha", "email": email, "password": "securepass"},
    )
    assert registration.status_code == 201
    assert "password_hash" not in registration.json()
    user_id = registration.json()["id"]

    login = client.post(
        "/users/login",
        json={"email": email, "password": "securepass"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    profile = client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["email"] == email
    remove_user(user_id)


def test_profile_is_user_scoped():
    first = client.post(
        "/users/register",
        json={"name": "Asha", "email": make_test_email(), "password": "securepass"},
    )
    second = client.post(
        "/users/register",
        json={"name": "Mina", "email": make_test_email(), "password": "securepass"},
    )
    login = client.post(
        "/users/login",
        json={"email": first.json()["email"], "password": "securepass"},
    )
    response = client.get(
        f"/users/{second.json()['id']}",
        headers={"Authorization": f"Bearer {login.json()['access_token']}",},
    )
    assert response.status_code == 403
    remove_user(first.json()["id"])
    remove_user(second.json()["id"])

@pytest.fixture
def registered_user():
    """A freshly registered user: (id, email, auth headers). Cleaned up after the test."""
    email = make_test_email()
    created = client.post("/users/register", json={"name": "Asha", "email": email, "password": "securepass"})
    assert created.status_code == 201
    token = client.post("/users/login", json={"email": email, "password": "securepass"}).json()["access_token"]
    yield created.json()["id"], email, {"Authorization": f"Bearer {token}"}
    remove_user(created.json()["id"])


def test_registration_never_stores_or_returns_plaintext_password(registered_user):
    user_id, _, headers = registered_user
    body = client.get(f"/users/{user_id}", headers=headers).json()
    assert "password" not in body and "password_hash" not in body
    db = SessionLocal()
    try:
        stored = db.get(User, user_id).password_hash
    finally:
        db.close()
    assert stored != "securepass"
    assert stored.startswith("$2")  # bcrypt


def test_duplicate_email_is_rejected_case_insensitively(registered_user):
    _, email, _ = registered_user
    for variant in (email, email.upper()):
        response = client.post("/users/register", json={"name": "Copy", "email": variant, "password": "securepass"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Email is already registered"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "A", "email": "not-an-email", "password": "securepass"},
        {"name": "A", "email": "ok@example.com", "password": "short"},
        {"name": "", "email": "ok@example.com", "password": "securepass"},
        {"email": "ok@example.com", "password": "securepass"},
    ],
    ids=["invalid-email", "weak-password", "empty-name", "missing-name"],
)
def test_registration_validation_errors(payload):
    assert client.post("/users/register", json=payload).status_code == 422


def test_invalid_login_gives_same_error_for_wrong_password_and_unknown_email(registered_user):
    _, email, _ = registered_user
    wrong_password = client.post("/users/login", json={"email": email, "password": "wrongpass1"})
    unknown_email = client.post("/users/login", json={"email": make_test_email(), "password": "securepass"})
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()  # must not reveal which emails exist


def test_profile_requires_a_token(registered_user):
    user_id, _, _ = registered_user
    assert client.get(f"/users/{user_id}").status_code == 401
    assert client.get(f"/users/{user_id}", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_expired_token_is_rejected(registered_user):
    user_id, _, _ = registered_user
    expired = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    assert client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


@pytest.mark.parametrize("known_secret", ["replace_with_a_long_random_secret", "change-this-secret", "secret"])
def test_token_forged_with_a_guessable_secret_is_rejected(registered_user, known_secret):
    """Regression for the placeholder-JWT-secret vulnerability: attackers try the well-known defaults."""
    user_id, _, _ = registered_user
    forged = jwt.encode({"sub": str(user_id)}, known_secret, algorithm="HS256")
    assert client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_for_a_deleted_user_is_rejected():
    email = make_test_email()
    user_id = client.post("/users/register", json={"name": "Gone", "email": email, "password": "securepass"}).json()["id"]
    token = client.post("/users/login", json={"email": email, "password": "securepass"}).json()["access_token"]
    remove_user(user_id)
    assert client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_profile_update_and_cannot_update_someone_else(registered_user):
    user_id, _, headers = registered_user
    updated = client.put(f"/users/{user_id}", headers=headers, json={"name": "New Name"})
    assert updated.status_code == 200 and updated.json()["name"] == "New Name"
    assert client.put(f"/users/{user_id + 100000}", headers=headers, json={"name": "Hacked"}).status_code == 403


def test_profile_update_cannot_take_another_users_email(registered_user):
    _, _, headers = registered_user
    other_email = make_test_email()
    other_id = client.post("/users/register", json={"name": "Other", "email": other_email, "password": "securepass"}).json()["id"]
    try:
        my_id = int(jwt.get_unverified_claims(headers["Authorization"].split()[1])["sub"])
        response = client.put(f"/users/{my_id}", headers=headers, json={"email": other_email})
        assert response.status_code == 400
    finally:
        remove_user(other_id)


def test_login_password_change_takes_effect(registered_user):
    user_id, email, headers = registered_user
    assert client.put(f"/users/{user_id}", headers=headers, json={"password": "brandnewpass1"}).status_code == 200
    assert client.post("/users/login", json={"email": email, "password": "securepass"}).status_code == 401
    assert client.post("/users/login", json={"email": email, "password": "brandnewpass1"}).status_code == 200
