# 30 Teststrategie

Jeder Test trägt `@pytest.mark.req("<ID>")`; `scripts/check_traceability.py` prüft, dass jede beschlossene
Anforderung auf allen Ebenen ihrer Spalte „Ebenen" getestet ist.

| Ebene | Ort | Umgebung | Inhalt |
| --- | --- | --- | --- |
| unit | `tests/unit` | nur Kern | jede Kernregel, Abnahmeszenarien, Kernisolation, Übersetzungen/Hilfetexte, Release- und Spec-Prüfungen. Abdeckung Kern ≥ 90 % |
| integration | `tests/integration` | pytest-homeassistant-custom-component | Config Flow, Subentries, Options, mehrere Anlagen, Hilfeschalter, Regelzyklen gegen Fake-Innengeräte (`fakes.FakeUnits`: gemerkter Sollwert je Modus, kein Sollwert in Lüften/Entfeuchten) |
| e2e | `tests/e2e` | echte Home-Assistant-Instanz (Compose-Dienst `homeassistant`, Version = `HA_IMAGE_TAG`) mit Simulator | Konfigurationsprüfung, Einrichtung des Referenzfalls über die echte REST-/WebSocket-API, Plan lesen, Sollwert nach Moduswechsel, Rückfall |

## Simulator (`tests/e2e/simulator`)

Test-Integration `climate_control_sim`, eingebunden über `.devcontainer/docker-compose.yml` und
`tests/e2e/ha_config/configuration.yaml`:

- sieben Klima-Entitäten mit den Namen aus `config/reference-case.yaml`;
- Heizen, während ein anderes Gerät kühlt/entfeuchtet → Gerät springt auf Kühlen (Konflikt);
- Wechsel auf Heizen/Kühlen setzt gemerkten Sollwert (18/26 °C); Lüften/Entfeuchten ohne Sollwert;
- `current_temperature` in ganzen Grad;
- `sensor.klima_aussen_leistung_w` (Lüfter + Nennleistung anfordernder Geräte);
- `sensor.sim_planner_power` (kW, `forecast`), steuerbar über Dienste `set_plan`, `set_reading`, `reset`.

## Hinweise

- Das HA-Test-Plugin sperrt Netz und DNS je Test; `tests/e2e/conftest.py` hebt das für e2e auf.
- e2e läuft nie gegen die produktive Instanz (`HA_URL`, Standard `http://homeassistant:8123`).
- Die e2e-Instanz wird beim ersten Lauf automatisch eingerichtet (Onboarding-Nutzer `e2e`).
