"""The HA-level budget test reuses the integration fixtures; the core test runs without Home Assistant."""

import contextlib

with contextlib.suppress(ImportError):  # core-only run (e.g. arm64 emulation without Home Assistant)
    from tests.integration.conftest import auto_enable_custom_integrations, units  # noqa: F401
