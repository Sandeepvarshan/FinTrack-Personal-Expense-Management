"""API Gateway tests.

The gateway's only job is to forward requests to the right service and translate failures
into correct HTTP status codes. So we replace the "internet" behind it with a fake upstream
(httpx.MockTransport). No database, no real services - fast and deterministic.
"""
import importlib.util
import logging
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

SERVICE_PATH = Path(__file__).parents[2] / "backend" / "api-gateway"
package_spec = importlib.util.spec_from_file_location(
    "gateway_app", SERVICE_PATH / "app" / "__init__.py", submodule_search_locations=[str(SERVICE_PATH / "app")]
)
gateway_app = importlib.util.module_from_spec(package_spec)
sys.modules["gateway_app"] = gateway_app
package_spec.loader.exec_module(gateway_app)

import gateway_app.main as gateway_main  # noqa: E402

SERVICE_URLS = gateway_main.SERVICE_URLS


@pytest.fixture
def upstream(monkeypatch):
    """Install a fake upstream. Set `upstream.handler = fn(request) -> httpx.Response` per test."""

    class Upstream:
        seen: list[httpx.Request] = []
        handler = staticmethod(lambda request: httpx.Response(200, json={"ok": True}))

    fake = Upstream()
    fake.seen = []

    def transport_handler(request: httpx.Request) -> httpx.Response:
        fake.seen.append(request)
        return fake.handler(request)

    monkeypatch.setattr(
        gateway_main,
        "make_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(transport_handler), timeout=timeout),
    )
    return fake


@pytest.fixture
def client():
    # follow_redirects=False so a 307 would be visible as a failure instead of silently followed
    return TestClient(gateway_main.app, follow_redirects=False)


def test_routes_each_prefix_to_its_own_service(client, upstream):
    for prefix, base_url in SERVICE_URLS.items():
        upstream.seen.clear()
        response = client.get(f"/{prefix}/1")
        assert response.status_code == 200
        assert str(upstream.seen[0].url) == f"{base_url.rstrip('/')}/{prefix}/1"


def test_collection_url_without_trailing_slash_is_not_redirected(client, upstream):
    # Regression: "/expenses" used to answer 307 -> "/expenses/" (extra round trip, breaks some clients)
    for prefix in SERVICE_URLS:
        response = client.get(f"/{prefix}")
        assert response.status_code == 200, f"/{prefix} answered {response.status_code}"
        assert upstream.seen[-1].url.path == f"/{prefix}"


def test_query_string_body_and_method_are_forwarded(client, upstream):
    response = client.post("/budgets?month=9", json={"amount": "100"})
    assert response.status_code == 200
    forwarded = upstream.seen[0]
    assert forwarded.method == "POST"
    assert forwarded.url.params["month"] == "9"
    assert b'"amount"' in forwarded.content


def test_authorization_header_is_forwarded_and_host_is_rewritten(client, upstream):
    client.get("/expenses", headers={"Authorization": "Bearer abc.def.ghi", "Host": "evil.example"})
    forwarded = upstream.seen[0]
    assert forwarded.headers["authorization"] == "Bearer abc.def.ghi"
    assert forwarded.headers["host"] != "evil.example"


@pytest.mark.parametrize("status_code", [201, 204, 400, 401, 403, 404, 409, 422, 500])
def test_upstream_status_codes_pass_through(client, upstream, status_code):
    upstream.handler = lambda request: httpx.Response(status_code, json={"detail": "from service"} if status_code != 204 else None)
    response = client.get("/categories/9")
    assert response.status_code == status_code
    if status_code != 204:
        assert response.json() == {"detail": "from service"}


def test_unknown_service_returns_404(client, upstream):
    response = client.get("/not-a-service/anything")
    assert response.status_code == 404
    assert response.json()["detail"] == "Service route not found"
    assert upstream.seen == []


def test_unreachable_service_returns_503(client, upstream):
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    upstream.handler = refuse
    response = client.get("/expenses")
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_slow_service_returns_504(client, upstream):
    def too_slow(request):
        raise httpx.ReadTimeout("read timed out")

    upstream.handler = too_slow
    assert client.get("/reports/monthly").status_code == 504


def test_garbled_upstream_response_returns_502(client, upstream):
    def garbled(request):
        raise httpx.RemoteProtocolError("server disconnected")

    upstream.handler = garbled
    assert client.get("/users/1").status_code == 502


def test_health_endpoint_is_not_swallowed_by_proxy_and_reports_each_service(client, upstream):
    def by_service(request: httpx.Request) -> httpx.Response:
        if request.url.port == 8003:
            raise httpx.ConnectError("down")
        if request.url.port == 8004:
            return httpx.Response(500)
        return httpx.Response(200, json={"status": "ok"})

    upstream.handler = by_service
    body = client.get("/health").json()
    assert body["service"] == "api-gateway"
    assert body["services"]["users"] == "ok"
    assert body["services"]["categories"] == "unavailable"
    assert body["services"]["budgets"] == "unhealthy"


def test_request_id_is_generated_forwarded_and_returned(client, upstream):
    response = client.get("/expenses")
    request_id = response.headers["x-request-id"]
    assert request_id
    assert upstream.seen[0].headers["x-request-id"] == request_id
    # a caller-supplied id is kept, so one id can be followed across services in the logs
    assert client.get("/expenses", headers={"X-Request-ID": "trace-123"}).headers["x-request-id"] == "trace-123"


def test_logs_never_contain_tokens_or_bodies(client, upstream, caplog):
    secret_token = "Bearer super.secret.token"
    with caplog.at_level(logging.INFO, logger="api-gateway"):
        client.post("/users/login", headers={"Authorization": secret_token}, json={"password": "hunter2hunter2"})
    assert "POST /users/login -> 200" in caplog.text
    assert "super.secret.token" not in caplog.text
    assert "hunter2" not in caplog.text
