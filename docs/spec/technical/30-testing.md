# 30 Teststrategie

Jeder Test trägt `@pytest.mark.req("<ID>")`; `scripts/check_traceability.py` prüft, dass jede beschlossene
Anforderung auf allen Ebenen ihrer Spalte „Ebenen" getestet ist.

| Ebene | Ort | Umgebung | Inhalt |
| --- | --- | --- | --- |
| unit | `tests/unit` | nur Kern | jede Kernregel, Abnahmeszenarien, Kernisolation, Übersetzungen/Hilfetexte, Release- und Spec-Prüfungen. Abdeckung Kern ≥ 90 % |
| integration | `tests/integration` | pytest-homeassistant-custom-component | Config Flow, Subentries, Options, mehrere Anlagen, Hilfeschalter, Betriebsart-Schalter, Lernen mit Speicherung und Reset, Aufzeichnung, Regelzyklen gegen Fake-Innengeräte (`fakes.FakeUnits`: gemerkter Sollwert je Modus, kein Sollwert in Lüften/Entfeuchten) |
| e2e | `tests/e2e` | echte Home-Assistant-Instanz (Compose-Dienst `homeassistant`, Version = `HA_IMAGE_TAG`) mit Simulator | Konfigurationsprüfung, Einrichtung des Referenzfalls über die echte REST-/WebSocket-API, Plan lesen, Sollwert nach Moduswechsel, Rückfall, Kühlbetrieb über den Schalter, Reset der gelernten Kapazität |

## Simulator (`tests/e2e/simulator`)

Test-Integration `climate_control_sim`, eingebunden über `.devcontainer/docker-compose.yml` und
`tests/e2e/ha_config/configuration.yaml`:

- sieben Klima-Entitäten mit den Namen aus `config/reference-case.yaml`;
- Heizen, während ein anderes Gerät kühlt/entfeuchtet → Gerät springt auf Kühlen (Konflikt);
- Wechsel auf Heizen/Kühlen setzt gemerkten Sollwert (18/26 °C); Lüften/Entfeuchten ohne Sollwert;
- `current_temperature` in ganzen Grad (gröber als die 0,5-K-Schritte der echten Geräte, die Regelung rundet nicht);
- `sensor.klima_aussen_leistung_w` (Lüfter + Nennleistung anfordernder Geräte);
- `sensor.sim_planner_power` (kW, `forecast`), steuerbar über Dienste `set_plan`, `set_reading`, `reset`;
- `input_boolean.sim_cooling` (in `configuration.yaml`): Kühlen-Schalter der Anlage (FR-SEAS-01).

## Hinweise

- Das HA-Test-Plugin sperrt Netz und DNS je Test; `tests/e2e/conftest.py` hebt das für e2e auf.
- e2e läuft nie gegen die produktive Instanz (`HA_URL`, Standard `http://homeassistant:8123`).
- Die e2e-Instanz wird beim ersten Lauf automatisch eingerichtet (Onboarding-Nutzer `e2e`).

## Performance (Zielplattform Raspberry Pi 5)

`tests/performance` (ohne Anforderungs-ID, läuft in CI): ein simulierter Tag mit 1440 Zyklen im Kern
(7 und 30 Räume, Plan mit 48 Stunden Prognose) und 2 × 200 Zyklen in Home Assistant mit 7 Innengeräten.
Zeit und Speicher werden in getrennten Läufen gemessen (Speicher-Tracing verlangsamt Python stark).

Messung vom 22.10.2026, HA-Stresstest aktualisiert am 23.10.2026:

| Messung | x86 (Entwicklungsrechner) | arm64 unter QEMU-Emulation |
| --- | --- | --- |
| Kern, 7 Räume, je Zyklus | Mittel 0,33 ms, max. 0,8 ms | Mittel 6,5 ms, max. 17 ms |
| Kern, 30 Räume, je Zyklus | Mittel 0,45 ms, max. 1,8 ms | Mittel 8,1 ms, max. 22 ms |
| Speicherzuwachs nach Aufwärmen, 1 bzw. 3 Tage | < 1 KiB (kein Wachstum) | < 1 KiB |
| HA-Zyklus, nichts ändert sich | Mittel 3 ms, 0 Dienstaufrufe, 0 Zustandsänderungen | – |
| HA-Zyklus, jede Minute ändert sich eine Gerätetemperatur (Stresstest) | Mittel 27 ms, max. 52 ms (inkl. Dienstaufrufe), 3,3 Dienstaufrufe und 4,1 Zustandsänderungen je Zyklus (seit 0.3 inkl. Diagnose-Sensoren je Raum) | – |

Einordnung (Schätzung, nicht auf einem Pi 5 gemessen): Die Emulation ist etwa 20-mal langsamer als x86; ein
echter Pi 5 ist nach veröffentlichten Einkern-Benchmarks etwa 3- bis 4-mal langsamer als x86. Erwartet werden
damit rund 1–2 ms Kern und 10–15 ms HA-Zyklus je Minute im Normalfall, das sind deutlich unter 0,1 % eines
Kerns. Die Event-Loop dürfte auch im Stresstest nur einige zehn Millisekunden je Minute belegt sein.

Maßnahmen aus der Messung:

- Prognose-Attribute (`forecast`) werden nicht im Recorder gespeichert (`_unrecorded_attributes`); sie sind
  groß und ändern sich mindestens stündlich. Ohne Änderung entstehen keine Recorder-Zeilen.
- Befehle an die Innengeräte nur bei Änderung. Im Stresstest wechseln Rangfolge und Sollwerte häufig; die
  offene Mindestlaufzeit je Gerät (FR-DIST-03) würde die Zahl der Befehle weiter senken.
