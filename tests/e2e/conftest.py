"""e2e fixtures: talk to a real Home Assistant (devcontainer service). Never to the production instance."""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Iterator

import pytest
import requests

_REAL_GETADDRINFO = socket.getaddrinfo


def _allow_network() -> None:
    """The HA test-harness plugin blocks network and DNS for every test; e2e needs the real instance."""
    try:
        import pytest_socket
    except ImportError:
        return
    pytest_socket._remove_restrictions()
    socket.getaddrinfo = _REAL_GETADDRINFO


@pytest.fixture(scope="session", autouse=True)
def _network_for_session() -> None:
    _allow_network()


@pytest.fixture(autouse=True)
def _network_for_test() -> None:
    _allow_network()


HA_URL = os.environ.get("HA_URL", "http://homeassistant:8123").rstrip("/")
CLIENT_ID = f"{HA_URL}/"
USER = {"name": "e2e", "username": "e2e", "password": "e2e-Passw0rd!", "language": "en"}


def _wait_ready(timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{HA_URL}/api/onboarding", timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError(f"Home Assistant not reachable at {HA_URL}")


def _token_from_code(code: str) -> str:
    r = requests.post(
        f"{HA_URL}/auth/token",
        data={"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID},
        timeout=10,
    )
    r.raise_for_status()
    return str(r.json()["access_token"])


def _login_token() -> str:
    r = requests.post(
        f"{HA_URL}/auth/login_flow",
        json={
            "client_id": CLIENT_ID,
            "handler": ["homeassistant", None],
            "redirect_uri": CLIENT_ID,
        },
        timeout=10,
    )
    r.raise_for_status()
    flow = r.json()["flow_id"]
    r = requests.post(
        f"{HA_URL}/auth/login_flow/{flow}",
        json={"client_id": CLIENT_ID, "username": USER["username"], "password": USER["password"]},
        timeout=10,
    )
    r.raise_for_status()
    return _token_from_code(r.json()["result"])


@pytest.fixture(scope="session")
def ha_token() -> str:
    """Onboard a fresh instance (or log in if already onboarded) and return an access token."""
    if os.environ.get("HA_TOKEN"):
        return os.environ["HA_TOKEN"]
    _wait_ready()
    r = requests.post(f"{HA_URL}/api/onboarding/users", json={"client_id": CLIENT_ID, **USER}, timeout=15)
    if r.status_code == 200:
        return _token_from_code(r.json()["auth_code"])
    return _login_token()


@pytest.fixture(scope="session")
def ha(ha_token: str) -> Iterator[requests.Session]:
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {ha_token}"
    session.base_url = HA_URL  # type: ignore[attr-defined]
    yield session
