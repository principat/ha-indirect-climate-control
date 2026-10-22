# Simulator für die e2e-Instanz

Test-Integration `climate_control_sim` (nur für e2e, nicht Teil der Auslieferung). Sie bildet den Referenzfall
nach: sieben Klima-Entitäten, Moduskonflikt am Außengerät, gemerkter Sollwert je Modus, ganze Grad,
Außenleistung abhängig von laufenden Geräten, Planer-Ausgabe mit `forecast`. Eingebunden über
`.devcontainer/docker-compose.yml` und `tests/e2e/ha_config/configuration.yaml`. Details: `docs/spec/technical/30-testing.md`.

Dienste: `climate_control_sim.set_plan` (`power_kw`, `hours`, `offset_h`, `available`),
`climate_control_sim.set_reading` (`unit`, `temperature`), `climate_control_sim.reset`.
