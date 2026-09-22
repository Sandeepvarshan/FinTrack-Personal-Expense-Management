import logging
import time
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .config import REQUEST_TIMEOUT, SERVICE_URLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-gateway")

app = FastAPI(title="FinTrack API Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# Headers we must not copy verbatim between the browser <-> gateway <-> service hops.
SKIP_REQUEST_HEADERS = {"host", "content-length"}
# httpx already decompresses the body, so passing "content-encoding" on would corrupt it.
SKIP_RESPONSE_HEADERS = {"content-length", "transfer-encoding", "connection", "content-encoding"}
PROXIED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def make_client(timeout: float) -> httpx.AsyncClient:
    """The one place an outgoing HTTP client is built (tests swap this for a fake upstream)."""
    return httpx.AsyncClient(timeout=timeout)


def forwarded_headers(request: Request, request_id: str) -> dict[str, str]:
    headers = {key: value for key, value in request.headers.items() if key.lower() not in SKIP_REQUEST_HEADERS}
    headers["x-request-id"] = request_id
    return headers


def error_response(status_code: int, detail: str, request_id: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers={"X-Request-ID": request_id})


# NOTE: /health is registered BEFORE the catch-all proxy routes below. FastAPI matches routes
# in registration order, so the proxy would otherwise swallow it.
@app.get("/health", tags=["health"])
async def health() -> dict[str, object]:
    statuses: dict[str, str] = {}
    async with make_client(2) as client:
        for name, base_url in SERVICE_URLS.items():
            try:
                response = await client.get(f"{base_url}/health")
                statuses[name] = "ok" if response.is_success else "unhealthy"
            except httpx.HTTPError:
                statuses[name] = "unavailable"
    return {"status": "ok", "service": "api-gateway", "services": statuses}


# Two routes -> one handler: "/expenses" (collection) and "/expenses/5" (item).
# Without the first, Starlette answers "/expenses" with a 307 redirect to "/expenses/".
@app.api_route("/{service}", methods=PROXIED_METHODS)
@app.api_route("/{service}/{path:path}", methods=PROXIED_METHODS)
async def proxy(service: str, request: Request, path: str = "") -> Response:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    service_url = SERVICE_URLS.get(service)
    if service_url is None:
        return error_response(404, "Service route not found", request_id)

    target = f"{service_url.rstrip('/')}/{service}{('/' + path) if path else ''}"
    started = time.perf_counter()
    try:
        async with make_client(REQUEST_TIMEOUT) as client:
            upstream = await client.request(
                request.method,
                target,
                params=request.query_params,
                content=await request.body(),
                headers=forwarded_headers(request, request_id),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout) as error:
        logger.error("request_id=%s service=%s unavailable (%s)", request_id, service, error.__class__.__name__)
        return error_response(503, f"{service} service is unavailable", request_id)
    except httpx.TimeoutException as error:
        logger.error("request_id=%s service=%s timed out (%s)", request_id, service, error.__class__.__name__)
        return error_response(504, f"{service} service timed out", request_id)
    except httpx.HTTPError as error:
        logger.error("request_id=%s service=%s bad upstream response (%s)", request_id, service, error.__class__.__name__)
        return error_response(502, f"{service} service returned an invalid response", request_id)

    elapsed_ms = (time.perf_counter() - started) * 1000
    # Only method, path, status and timing are logged - never headers, tokens, bodies or query strings.
    logger.info(
        "request_id=%s %s /%s%s -> %s service=%s %.0fms",
        request_id, request.method, service, f"/{path}" if path else "", upstream.status_code, service, elapsed_ms,
    )
    response_headers = {
        key: value for key, value in upstream.headers.items() if key.lower() not in SKIP_RESPONSE_HEADERS
    }
    response_headers["X-Request-ID"] = request_id
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
