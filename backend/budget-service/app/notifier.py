import logging

import httpx

from .config import settings

logger = logging.getLogger("budget-service")


def make_client(timeout: float) -> httpx.Client:
    """The one place an outgoing HTTP client is built (tests swap this to reach a fake/in-process service)."""
    return httpx.Client(timeout=timeout)


def send_notification(token: str, notification_type: str, message: str) -> bool:
    """Ask the Notification Service to store one notification for the token's owner.

    Never raises. A broken or slow Notification Service must not make budget operations fail;
    the failure is logged and reported through the return value instead.
    """
    url = f"{settings.notification_service_url.rstrip('/')}/notifications"
    try:
        with make_client(settings.downstream_timeout_seconds) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"message": message, "type": notification_type},
            )
    except httpx.HTTPError as error:
        logger.warning("notification-service unreachable: %s", error.__class__.__name__)
        return False
    if not response.is_success:
        logger.warning("notification-service rejected alert: status=%s", response.status_code)
        return False
    return True
