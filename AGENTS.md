# Arbeitsanweisungen (Codex / VS Code)

Projekt: generische Home-Assistant-Integration "Climate Control". Sie steuert eine Klimaanlage
(mehrere Innengeräte, ein Außengerät) so, dass sie dem Plan eines Energie-Planers (Referenz: HAEO)
folgt. Der Referenzfall (LG Multi V, 7 Innengeräte) ist nur Entwicklungstemplate, nicht Teil des Kerns.

## Dokumentenschichten (strikt trennen)

| Schicht | Ort | Rolle | Pflege |
| --- | --- | --- | --- |
| Fachliche Spezifikation | `docs/spec/functional/` | WAS, technologiefrei, einzige Quelle der Wahrheit | nur auf ausdrückliche Anweisung des Nutzers ändern |
| Rahmenbedingungen | `docs/environment/` | gegebene Fakten (Versionen, Geräteverhalten, vorhandene Objekte) | Fakten ergänzen/korrigieren |
| Technische Spezifikation | `docs/spec/technical/` | WIE, abgeleitet aus fachlich + Rahmenbedingungen | wegwerfbar, wird bei Regeneration gelöscht |
| Code und Tests | `custom_components/`, `tests/`, `scripts/` | abgeleitet | wird bei Regeneration neu erzeugt |

Regeln:
- Die fachliche Spezifikation enthält keine Technologiebegriffe (Prüfung: `python scripts/check_spec_separation.py`).
- Technische Entscheidungen stehen nie in `docs/spec/functional/`.
- Technische Spezifikation nie als Eingabe für eine Regeneration verwenden. Ablauf: `docs/REGENERATION.md`.
- Instanzdaten (Entitäten, Flächen) stehen in `config/`, nicht in der Spezifikation.

## Qualitätsregeln

- Keine Funktion ohne Test. Jede fachliche Anforderung mit Status `beschlossen` hat Tests auf allen Ebenen,
  die in ihrer Spalte "Ebenen" stehen. Tests tragen `@pytest.mark.req("FR-...")`.
  Prüfung: `python scripts/check_traceability.py` (CI bricht bei Lücken ab).
- Ebenen: `unit` (Kern ohne Home Assistant), `integration` (pytest-homeassistant-custom-component),
  `e2e` (echte Home-Assistant-Instanz im Devcontainer, gegen die Konfiguration geprüft wird).
- `custom_components/climate_control/core/` importiert nie `homeassistant` (Test erzwingt das).
- Konfiguration (`config/*.yaml`, Config Flow, Services) wird im e2e-Test gegen die echte Instanz geprüft
  (`/api/config/core/check_config`, Integration geladen, Entitäten vorhanden).
- Ungeprüfte Annahmen als solche kennzeichnen. Nichts behaupten, was nicht gemessen oder getestet ist.

## Sicherheitsregeln

- Die produktive Home-Assistant-Instanz des Nutzers wird nie angesprochen oder geändert.
  Alle Läufe gehen gegen den Home Assistant im Devcontainer (`HA_URL`, Standard `http://homeassistant:8123`).
- Keine Änderung an Planer-Konfiguration oder realen Geräten ohne ausdrückliche Freigabe des Nutzers.

## Befehle

```
pip install -e ".[dev]" && npm ci          # einmalig (macht der Devcontainer)
pytest tests/unit                          # Kern
pytest tests/integration                   # Integration mit HA-Testharness
pytest tests/e2e                           # echte HA-Instanz (docker compose up -d homeassistant)
python scripts/check_spec_separation.py    # Fachspec technologiefrei?
python scripts/check_traceability.py       # jede Anforderung getestet?
ruff check . && ruff format --check . && mypy custom_components
```

## Commits und Release

- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`; `!` oder `BREAKING CHANGE:` für Major).
- Version und `CHANGELOG.md` entstehen nur durch semantic-release (`.releaserc.json`). Nie von Hand ändern.
- Release läuft automatisch im CI-Job `release` auf `main`, nachdem alle Prüfungen grün sind.

## Definition of Done

1. Anforderung in der Fachspec vorhanden und `beschlossen`.
2. Tests auf allen geforderten Ebenen grün, Traceability grün.
3. Lint, Typen, hassfest und HACS-Validierung grün.
4. Technische Spec spiegelt die Umsetzung (abgeleitet, nicht Quelle).
