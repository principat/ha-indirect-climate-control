import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "req(id): fachliche Anforderung")
