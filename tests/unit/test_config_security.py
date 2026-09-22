"""Unit tests for the startup guard on JWT_SECRET (no database, no network, milliseconds)."""
import importlib.util
from pathlib import Path

import pytest

BACKEND = Path(__file__).parents[2] / "backend"
SERVICES = ["user", "expense", "category", "budget", "report", "notification"]
STRONG_SECRET = "x" * 20 + "Y" * 20  # 40 chars, not a known placeholder


def load_config(service: str):
    """Import <service>-service/app/config.py fresh, as if the service were starting up."""
    path = BACKEND / f"{service}-service" / "app" / "config.py"
    spec = importlib.util.spec_from_file_location(f"config_under_test_{service}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize(
    "bad_secret",
    ["", "change-this-secret", "replace_with_a_long_random_secret", "too-short-secret"],
    ids=["empty", "old-default", "env-example-placeholder", "shorter-than-32"],
)
def test_service_refuses_to_start_with_weak_jwt_secret(service, bad_secret, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", bad_secret)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        load_config(service)


@pytest.mark.parametrize("service", SERVICES)
def test_service_starts_with_strong_jwt_secret(service, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", STRONG_SECRET)
    assert load_config(service).settings.jwt_secret == STRONG_SECRET


def test_error_message_never_echoes_the_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "hunter2-but-short")
    with pytest.raises(RuntimeError) as failure:
        load_config("user")
    assert "hunter2" not in str(failure.value)
