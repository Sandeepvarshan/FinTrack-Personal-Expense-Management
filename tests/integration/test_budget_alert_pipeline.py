"""Integration test: Expense Service -> Budget Service -> Notification Service.

All three services are loaded in one process and their HTTP calls to each other are "bridged"
straight into each other's FastAPI apps. That is real service code, real HTTP request/response
objects and the real MySQL database - only the network hop is replaced, so the test is fast
and needs no running servers.
"""
import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import text

BACKEND = Path(__file__).parents[2] / "backend"


def load_service(directory: str, package_name: str):
    path = BACKEND / directory
    spec = importlib.util.spec_from_file_location(
        package_name, path / "app" / "__init__.py", submodule_search_locations=[str(path / "app")]
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    return package


load_service("expense-service", "pipe_expense")
load_service("budget-service", "pipe_budget")
load_service("notification-service", "pipe_notification")

import pipe_budget.notifier as budget_notifier  # noqa: E402
import pipe_expense.budget_client as expense_budget_client  # noqa: E402
from pipe_budget.database import SessionLocal  # noqa: E402
from pipe_budget.config import settings  # noqa: E402
from pipe_budget.main import app as budget_app  # noqa: E402
from pipe_expense.main import app as expense_app  # noqa: E402
from pipe_notification.main import app as notification_app  # noqa: E402

expense_client = TestClient(expense_app)
budget_client = TestClient(budget_app)
notification_client = TestClient(notification_app)

MONTH, YEAR = 3, 2031


def bridge_to(target: TestClient):
    """An httpx transport that hands the request to `target` instead of the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        forwarded = {k: v for k, v in request.headers.items() if k.lower() in ("authorization", "content-type")}
        reply = target.request(request.method, request.url.raw_path.decode(), content=request.content, headers=forwarded)
        return httpx.Response(reply.status_code, content=reply.content, headers={"content-type": reply.headers.get("content-type", "application/json")})

    return handler


def client_factory(transport_handler):
    return lambda timeout: httpx.Client(transport=httpx.MockTransport(transport_handler), timeout=timeout)


def unreachable(request):
    raise httpx.ConnectError("connection refused")


@pytest.fixture(autouse=True)
def wired_services(monkeypatch):
    monkeypatch.setattr(expense_budget_client, "make_client", client_factory(bridge_to(budget_client)))
    monkeypatch.setattr(budget_notifier, "make_client", client_factory(bridge_to(notification_client)))


def make_user(name: str = "Pipeline User") -> dict:
    db = SessionLocal()
    try:
        user_id = db.execute(
            text("INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'test-only')"),
            {"n": name, "e": f"pipeline-{uuid4().hex}@example.com"},
        ).lastrowid
        category_name = f"Pipeline Cat {uuid4().hex[:6]}"
        category_id = db.execute(
            text("INSERT INTO categories (user_id, name) VALUES (:u, :n)"), {"u": user_id, "n": category_name}
        ).lastrowid
        db.commit()
    finally:
        db.close()
    token = jwt.encode({"sub": str(user_id)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"id": user_id, "category_id": category_id, "category_name": category_name, "headers": {"Authorization": f"Bearer {token}"}}


def delete_user(user_id: int) -> None:
    db = SessionLocal()
    try:
        for table in ("notifications", "expenses", "budgets", "categories"):
            db.execute(text(f"DELETE FROM {table} WHERE user_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        db.commit()
    finally:
        db.close()


@pytest.fixture
def user():
    created = make_user()
    yield created
    delete_user(created["id"])


def add_expense(user: dict, amount: str, day: str = f"{YEAR}-{MONTH:02d}-10", **extra):
    response = expense_client.post(
        "/expenses",
        headers=user["headers"],
        json={"category_id": user["category_id"], "amount": amount, "expense_date": day, "payment_method": "Card", **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def add_budget(user: dict, amount: str, category: bool = True, month: int = MONTH):
    response = budget_client.post(
        "/budgets",
        headers=user["headers"],
        json={"category_id": user["category_id"] if category else None, "month": month, "year": YEAR, "amount": amount},
    )
    assert response.status_code == 201, response.text
    return response.json()


def notifications(user: dict) -> list[dict]:
    return notification_client.get("/notifications", headers=user["headers"]).json()


def test_spending_crossing_thresholds_creates_one_warning_and_one_exceeded_alert(user):
    add_budget(user, "100.00")

    add_expense(user, "50.00")  # 50% -> on track
    assert notifications(user) == []

    add_expense(user, "40.00")  # 90% -> warning
    found = notifications(user)
    assert [n["type"] for n in found] == ["budget_warning"]
    assert user["category_name"] in found[0]["message"] and "80%" in found[0]["message"]

    add_expense(user, "30.00")  # 120% -> exceeded
    add_expense(user, "5.00")  # still exceeded: must NOT create a duplicate
    assert sorted(n["type"] for n in notifications(user)) == ["budget_exceeded", "budget_warning"]


def test_alert_is_not_raised_for_budgets_of_other_months_or_other_categories(user):
    add_budget(user, "100.00", month=MONTH + 1)  # April budget
    add_expense(user, "500.00")  # March spending
    assert notifications(user) == []


def test_overall_budget_counts_spending_in_every_category(user):
    add_budget(user, "100.00", category=False)
    add_expense(user, "150.00")
    found = notifications(user)
    assert [n["type"] for n in found] == ["budget_exceeded"]
    assert "all categories" in found[0]["message"]


def test_creating_a_budget_that_is_already_exceeded_alerts_immediately(user):
    add_expense(user, "500.00")  # no budget yet -> nothing to alert on
    assert notifications(user) == []
    add_budget(user, "100.00")
    assert [n["type"] for n in notifications(user)] == ["budget_exceeded"]


def test_moving_an_expense_into_a_budgeted_month_triggers_the_check(user):
    add_budget(user, "100.00", month=MONTH)
    elsewhere = add_expense(user, "500.00", day=f"{YEAR}-{MONTH - 1:02d}-10")
    assert notifications(user) == []
    moved = expense_client.put(f"/expenses/{elsewhere['id']}", headers=user["headers"], json={"expense_date": f"{YEAR}-{MONTH:02d}-15"})
    assert moved.status_code == 200
    assert [n["type"] for n in notifications(user)] == ["budget_exceeded"]


def test_expense_is_saved_even_when_budget_service_is_down(user, monkeypatch):
    monkeypatch.setattr(expense_budget_client, "make_client", client_factory(unreachable))
    add_budget(user, "10.00")
    saved = add_expense(user, "999.00")  # add_expense asserts 201
    assert expense_client.get(f"/expenses/{saved['id']}", headers=user["headers"]).status_code == 200
    assert notifications(user) == []


def test_budget_evaluation_survives_notification_service_being_down(user, monkeypatch):
    add_budget(user, "10.00")
    monkeypatch.setattr(budget_notifier, "make_client", client_factory(unreachable))
    add_expense(user, "999.00")  # still 201
    result = budget_client.post("/budgets/evaluate", headers=user["headers"])
    assert result.status_code == 200
    assert result.json()[0]["status"] == "exceeded" and result.json()[0]["delivered"] is False


def test_evaluate_only_looks_at_the_callers_own_budgets(user):
    add_budget(user, "10.00")
    add_expense(user, "999.00")
    stranger = make_user("Stranger")
    try:
        assert budget_client.post("/budgets/evaluate", headers=stranger["headers"]).json() == []
        assert notifications(stranger) == []
    finally:
        delete_user(stranger["id"])


def test_evaluate_requires_authentication():
    assert budget_client.post("/budgets/evaluate").status_code == 401
