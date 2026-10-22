# 40 Veröffentlichung

- Commits nach Conventional Commits; `commitlint` im CI für Pull Requests, `conventional-pre-commit` lokal.
- CI (`.github/workflows/ci.yml`): `checks` (ruff, mypy, Spec-Trennung, unit + integration mit Abdeckung,
  Traceability), `validate` (hassfest, HACS), `e2e` (Home Assistant `HA_IMAGE_TAG` aus `.devcontainer/.env.example`).
- Job `release` nur auf `main` nach grünen Prüfungen: semantic-release bestimmt die Version, schreibt
  `CHANGELOG.md`, setzt die Version in `manifest.json` und `pyproject.toml` (`scripts/set_version.py`), committet
  und erstellt das GitHub-Release.
- Versionen und Änderungsprotokoll nie von Hand ändern.
- Home-Assistant-Version: `HA_IMAGE_TAG` und die Version von `pytest-homeassistant-custom-component` in
  `pyproject.toml` müssen dieselbe Home-Assistant-Version meinen (derzeit 2026.10.2, Python 3.14).
