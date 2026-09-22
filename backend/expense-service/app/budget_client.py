import logging

import httpx

from .config import settings

logger = logging.getLogger("expense-service")


def make_client(timeout: float) -> httpx.Client:
    """The one place an outgoing HTTP client is built (tests swap this to reach an in-process service)."""
    return httpx.Client(timeout=timeout)


def request_budget_check(token: str, month: int, year: int) -> None:
    """Tell the Budget Service that spending changed in this month so it can raise budget alerts.

    Runs after the expense response was already sent, and never raises: an expense must be saved
    even when the Budget Service is down.
    """
    url = f"{settings.budget_service_url.rstrip('/')}/budgets/evaluate"
    try:
        with make_client(settings.downstream_timeout_seconds) as client:
            response = client.post(url, params={"month": month, "year": year}, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as error:
        logger.warning("budget-service unreachable: %s", error.__class__.__name__)
        return
    if not response.is_success:
        logger.warning("budget-service rejected budget check: status=%s", response.status_code)
