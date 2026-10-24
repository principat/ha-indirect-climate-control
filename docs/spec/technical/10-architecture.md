# 10 Architektur

Abgeleitet aus `docs/spec/functional/` und den Rahmenbedingungen. Nicht Quelle der Wahrheit.

## Schichten

| Schicht | Ort | Inhalt | Abhängigkeiten |
| --- | --- | --- | --- |
| Kern | `custom_components/climate_control/core/` | gesamte Fachlogik, reine Funktionen und kleine zustandsbehaftete Klassen | nur Standardbibliothek, nie `homeassistant` (Test `test_core_isolation`) |
| Adapter | `custom_components/climate_control/*.py` | Config Flow, Coordinator, Entitäten, Dienst | Home Assistant + Kern |
| Simulator | `tests/e2e/simulator/custom_components/climate_control_sim/` | Innengeräte, Außenleistung, Planer-Ausgabe für die e2e-Instanz | Home Assistant |

## Kernmodule

| Modul | Anforderungen | Aufgabe |
| --- | --- | --- |
| `model.py` | – | `Mode` (Werte = HVAC-Modi), Klassen Kühl/Neutral, `RoomState`, `Command` |
| `config.py` | FR-GEN-01 | `RoomConfig`, `Parameters` (Startwerte aus Abschnitt 4), `InstallationConfig` mit Prüfung. Anlagenwerte (Pmin, Pmax, Kapazität, Räume) ohne Standardwert; den Startwert der Kapazität (7 kWh/K) setzt der Adapter |
| `plan.py` | FR-PLAN-01, FR-SAFE-04 | `Plan` aus Prognosepunkten, Leistung zu einem Zeitpunkt, Horizont, Gültigkeit; `plan_from_forecast` liest die Planer-Ausgabe |
| `threshold.py` | FR-PLAN-02, FR-PLAN-03 | Start-/Abschaltschwelle mit Hysterese, mindestens Pmin |
| `soc.py` | FR-SOC-01, FR-SOC-02 | Skala, schlechtester Raum, Ausreißerfilter, Median-Glättung |
| `distribution.py` | FR-DIST-01, FR-DIST-02 | Rangstufen nach Abweichung mit Gleichstand-Band, Gruppen je Leistungsklasse (= gleiche Nennleistung, kein eigenes Feld), Auswahl bis Nennleistung ≥ Anforderung |
| `diagnostics.py` | FR-OBS-02 | Abweichung, Wärmebedarf und Speicherkapazität je Raum aus den im Zyklus verwendeten Temperaturen |
| `modes.py` | FR-MODE-01 | nächster zulässiger Moduszustand (Heizen/Kühlen nur über neutral) |
| `planner_model.py` | FR-PLNR-01 | Vorgaben für den Planer inkl. Stundenprognosen |
| `controller.py` | alle obigen, FR-PLAN-04, FR-SAFE-01..04, FR-MODE-03, FR-SRC-01 | ein Regelzyklus |

## Datenfluss je Zyklus (`Controller.step`)

1. Gerätetemperatur je Raum lesen, auf ganze Grad runden, Ausreißerfilter (FR-SRC-01, FR-SOC-02).
2. Aktive Räume = Temperatur und Modus bekannt, Fenster zu.
3. SOC = Skala(Temperatur des Raums mit kleinster Differenz Temperatur − eigener Sollwert), Median über 15 min.
4. Überhitzungs-Zeitgeber je Raum führen.
5. Plan fehlt oder veraltet → zuerst Warten (`fallback_delay_s`, 600 s): Geräte unverändert, Schutz gilt. Danach Rückfall:
   schrittweise (`fallback_step_s`, 120 s) je eine Gruppe gleicher Nennleistung auf Heizen mit Standard-Sollwert,
   größte Abweichung zuerst; laufende Geräte bleiben an. Kommt der Plan zurück, beginnt beim nächsten Ausfall
   die Wartezeit von vorn. Hartes Minimum und Überhitzung gelten in jedem Zweig, Fenster überschreiben alles.
   Sonst: Schwellenentscheidung mit Hysterese und Mindestlaufzeit der Anlage (`min_run_s`, 600 s ab jedem Start, Halten
   mit mindestens Pmin, Zeitgeber nur bei Aus → An neu, keine Mindestpause), bei Betrieb Räume auswählen (Ziel = Gerätetemperatur + Heiz-Offset,
   höchstens Überlastgrenze), übrige neutral; hartes Minimum → Heizen; Überhitzung ≥ Dauer und kein Heizziel → Kühlen.
6. Offenes Fenster → neutral (überschreibt alles, auch den Rückfall).
7. `next_modes` gegen die aktuellen Modi: bei Konflikt zuerst alle nicht neutralen Geräte neutral.
8. Befehle nur für Heizen/Kühlen mit Sollwert.

Der Adapter (`coordinator.py`) führt den Zyklus im Intervall `cycle_s` aus, wendet nur Änderungen an und
setzt nach jedem Wechsel auf Heizen/Kühlen den Sollwert erneut (FR-MODE-02). Weicht der Sollwert des Geräts
später ab (z. B. verspätet übernommener gemerkter Wert), korrigiert der nächste Zyklus ihn.

## Annahmen (nicht in der Fachspec festgelegt, als Parameter konfigurierbar)

| Thema | Umsetzung | Parameter |
| --- | --- | --- |
| SOC-Bezug auf eigenen Sollwert (offener Punkt) | eigener Sollwert wählt den schlechtesten Raum, die Skala gilt für dessen absolute Temperatur | – |
| Gleichstand „innerhalb des Bandes" | Differenz zur größten Abweichung der Stufe < Band | `tie_band_k` |
| Leistung je Gerät | Sollwert = Gerätetemperatur + Offset | `heat_offset_k` = 1 K |
| Zahl der Geräte | ganze Gruppen, bis Summe der Nennleistungen ≥ Anforderung | Nennleistung je Innengerät |
| Ausreißer | einmal verworfen, bei Bestätigung im nächsten Zyklus übernommen | `outlier_k` |
| Fenster offen | Gerät neutral, nicht im SOC, nicht verteilt, auch im Rückfall | – |
| Plan veraltet | älter als `plan_max_age_s` (1800 s) oder Zeitpunkt außerhalb der Prognose | `plan_max_age_s` |
| Nachtabsenkung | senkt Untergrenze und hartes Minimum für den Planer um 1 K; Raumschutz unverändert | `night_setback_k` |
| Obergrenze ohne Aufschlag | 24 °C je Innengerät; für den Planer flächengewichtet gemittelt (wie die Überlastgrenze) | `comfort_max_c` je Innengerät |
| Aufschlag Überlast | 0,003 je kWh | `overcharge_cost` |
| Pufferkapazität | Startwert 3 kWh/K, keine Einstellung; Lernen siehe 50-capacity-learning.md (Konzept) | – |
| Aufschlag Spätladen „fällt mit der Zeit" | linear vom Startwert auf 0 über den Horizont, damit bei gleichem Preis später geladen wird | `late_charge_surcharge` |
| Gewichtung Untergrenzen | Fläche der Räume | Fläche je Innengerät |
| Kapazität je Raum (Diagnose) | Pufferkapazität nach Fläche auf die Räume verteilt | Fläche je Innengerät |

Nicht umgesetzt (Status nicht `beschlossen`): FR-DIST-03 (offen), FR-LOAD-01 und FR-OBS-01 (Vorschlag).
