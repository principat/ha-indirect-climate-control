# 20 Schnittstellen

## Konfiguration (FR-GEN-01, FR-CFG-01..03)

| Ebene | Ablauf | Gespeichert in |
| --- | --- | --- |
| Anlage | Config Flow `user`, änderbar über `reconfigure`: Name, Temperatureeinheit (`temperature_unit`: `celsius` Standard oder `fahrenheit`, FR-UNIT-01), Pmin, Pmax, Leistungssensor des Außengeräts (Pflicht, `outdoor_power_entity`; fehlt er in älteren Einträgen, erinnert eine Reparaturmeldung), Kühlen-Schalter optional (`season_entity`: `switch`, `binary_sensor`, `input_boolean`; aus oder fehlend = Heizen), Planer-Sensor(en) optional | `entry.data`, Titel |
| Innengerät | Subentry-Typ `room` („Innengerät hinzufügen" im Drei-Punkte-Menü des Eintrags), je Gerät einzeln anlegen, ändern (`reconfigure`), löschen: Klima-Entität, Name, Sollwert-Quelle (`setpoint_source`: `constant` oder `entity`, im zweiten Schritt der Wert `setpoint_c` oder die Entität `setpoint_entity` aus `input_number`, `number`, `sensor`; plausibel sind 5–30 °C bzw. 41–86 °F, sonst gilt der zuletzt gültige Wert, vor dem ersten der Raum nicht geregelt; ältere Einträge leiten die Quelle ab: Entität gesetzt = `entity`, ein dort gespeicherter fester Wert dient als Startwert), optional Regelbereich und absolute Grenze (`band_down`, `band_up`, `limit_down`, `limit_up`, Standard 2/2/3/3, in der Einheit der Anlage), optional Lüfterstufen (`fan_heat` beim Heizen unter der Steuerung der Anlage, `fan_neutral` danach, Textfelder, FR-FAN-01), optional Meldeschritt (`step`, Standard 0,5: kleinste gemeldete Änderung der Gerätetemperatur; ein gespeicherter `start_offset` früherer Versionen wird ignoriert), Nennleistung (bestimmt die Leistungsklasse), Fläche, Fensterkontakte (mehrere, offen = einer offen) | `entry.subentries`, `unique_id` = Klima-Entität (je Anlage nur einmal) |
| Parameter | Options Flow: Menü mit `plan` (Planer-Sensor) und `sensors` (Leistungssensor des Außengeräts, Kühlen-Schalter; beide schreiben `entry.data`, ein leeres Schalterfeld entfernt ihn) sowie den Gruppen `control`, `soc`, `safety`, `planner` (`help.PARAMETER_GROUPS`); jede Gruppe speichert zusammen mit den übrigen Werten | `entry.options` |
| Hilfeschalter | `help_expanded` | `entry.options` |
| Betriebsmodus | `select`-Entität `operating_mode` (`hems_optimized`, `hems_buffer`, `manufacturer`, `manufacturer_cycle`, FR-OPM-01), siehe `70-operating-modes.md` | `Store` der Anlage (`operating_mode`) |

- Mehrere Anlagen: beliebig viele Config Entries, keine Einschränkung auf eine Instanz (FR-CFG-02).
  Entitäts-IDs folgen dem Anlagennamen (`sensor.<name>_state_of_charge`).
- Reihenfolge der Innengeräte = Anlagereihenfolge der Subentries; Reihenfolge der Leistungsklassen (gleiche Nennleistung) = erstes Vorkommen.
- Ohne Innengerät läuft die Anlage leer, alle Entitäten sind `unavailable`.
- Ohne Planer-Sensor (Inbetriebnahme): SOC und Planer-Vorgaben werden berechnet und veröffentlicht, es gehen
  keine Befehle an die Innengeräte, `running` und `fallback` sind aus. Grund: Der Planer braucht zuerst die
  Sensoren dieser Integration, bevor es seine Ausgabe gibt (Reihenfolge in `README.md`).
- Neu geladen wird nur bei Änderungen, die die Regelung betreffen (Daten, wirksame Parameter, Innengeräte),
  nicht beim Hilfeschalter.

### Erklärtexte (FR-CFG-03)

Über jedem nicht trivialen Feld (alle außer Namen) steht ein einklappbarer Abschnitt `help_<feld>`.
Titel „Hilfe: <Feld>", Beschreibung = Erklärtext aus den Übersetzungen (`sections.help_<feld>.description`),
Inhalt = Hilfsschalter `help_expanded` („Hilfetexte beim Öffnen aufgeklappt"). Der Abschnitt ist eingeklappt,
wenn der gespeicherte Schalter aus ist. Weicht ein Schalter im abgeschickten Formular vom gespeicherten Wert ab,
wird der neue Wert gespeichert und gilt für alle Formulare der Anlage. Grund für diese Form: Home-Assistant-Formulare
kennen keinen einklappbaren Text ohne Feld, ein Abschnitt braucht mindestens ein Feld.

Texte: `strings.json`, `translations/en.json`, `translations/de.json` (gleiche Struktur, Test `test_help.py`).

## Schnittstelle zum Planer

### Eingang: Plan (FR-PLAN-01)

Ein oder mehrere Sensoren (konfigurierbar). Referenz: der geplante Fluss der HAEO-Verbindung Haus → Knoten
Klima (`sensor.<verbindung>_source_to_target_power`, HAEO 0.4.1; Format geprüft am 23.10.2026: kW, `forecast` als
`{time, value}` mit Zeitzone, Schritte 1 min bis 1 h), bei zwei HAEO-Verbindungen beide. Nicht die
Ladeleistung der Batterie: Am Knoten Klima hängt auch die Last Wärmebedarf, die HAEO direkt versorgen kann
(Topologie in `README.md`). Mehrere Sensoren werden je Zeitpunkt addiert
(`core.plan.combine`); der Summenplan ist so alt wie sein ältester Teil und endet mit dem kürzesten.
Fällt ein Sensor aus, gilt der Plan als fehlend. Zielbild der HAEO-Topologie: `README.md`.

- Zustand: Leistung jetzt, Einheit aus `unit_of_measurement` (`kW` → ×1000, sonst W).
- Attribut `forecast`: Liste von `{time|start_time, value}` oder Abbildung Zeit → Wert. Zeiten ISO 8601,
  ohne Zeitzone = Zeitzone des Empfangs.
- Ohne `forecast` gilt der Zustand allein als Plan ab Empfang.
- Empfangszeit = max(`last_updated`, `last_reported`).
- `unavailable`/`unknown` = Planer ausgefallen: erst Wartezeit, dann schrittweiser Rückfall (FR-SAFE-04). Gilt auch
  nach einem Neustart von Home Assistant, bis der Planer seinen ersten Plan liefert (hier etwa 4 Minuten).

Ungeprüfte Annahme: Das Ausgabeformat von HAEO-Sensoren entspricht dieser Form. Belegt ist nur, dass HAEO
Eingänge mit `forecast: [{time, value}]` liest (haeo.io, Stand 21.10.2026).

### Ausgang: Vorgaben für den Planer (FR-PLNR-01)

Sensoren je Anlage, Prognosen im Attribut `forecast: [{time, value}]` (stündlich, `planner_horizon_h`).

| Sensor (Schlüssel) | Einheit | Bedeutung, Zuordnung HAEO-Batterie |
| --- | --- | --- |
| `soc` | % | Current Charge Percentage, Attribut `worst_room`; im Kühlbetrieb gespiegelt (FR-SEAS-02) |
| `capacity` | kWh | Capacity = gelernte Kapazität je K der aktuellen Betriebsart (Startwert 3) × Skalenbreite |
| `min_charge` | % | Min Charge Percentage (unteres Ende des Regelbereichs, flächengewichtet, nachts abgesenkt), mit Prognose |
| `undercharge` | % | Undercharge Percentage (absolute Grenze unten, nachts abgesenkt), mit Prognose |
| `max_charge` | % | Max Charge Percentage (oberes Ende des Regelbereichs) |
| `overcharge` | % | Overcharge Percentage (absolute Grenze oben) |
| `undercharge_cost` / `overcharge_cost` | Währung/kWh | Undercharge/Overcharge Cost |
| `efficiency` | % | Charge/Discharge efficiency |
| `max_discharge_power` | kW | Max Discharge Power |
| `max_charge_power` | kW | Max Power der einen Verbindung Haus → Klima (Grundvariante, = Pmax) |
| `charge_cost` | Währung/kWh | Aufschlag Spätladen, mit fallender Prognose |

Alle Prozentwerte liegen fest auf der SOC-Skala der Räume (FR-SOC-01): absolute Grenze unten 0 %, Untergrenze des Regelbereichs 10 %,
Obergrenze 90 %, absolute Grenze oben 100 %; die Nachtabsenkung rückt die unteren Werte um die Absenkung nach unten (begrenzt auf 0 %). Im Kühlbetrieb (FR-SEAS-02) tauschen die Seiten: Regelbereich und absolute Grenze über dem Sollwert sind dann die
Entladeseite (Min Charge, Undercharge), die unter dem Sollwert die Ladeseite (Max Charge, Overcharge).

### Status

`planned_power` (W, Prognose), `requested_power` (W, Attribut `served_rooms`), `binary_sensor` `running`, `fallback` (an erst nach der Wartezeit; Attribut `plan_missing_s` = Sekunden ohne gültigen Plan).

Je Innengerät ein eigenes Gerät (Subentry), Diagnose-Sensoren `room_deviation` (K), `room_heat_demand` (kWh),
`room_storage` (kWh), `entity_category: diagnostic` (FR-OBS-02).

Je Innengerät zusätzlich `room_offset` (geplanter Offset = Schritte × Schrittweite, 0 wenn nicht bedient) und `room_step_power` (W): gelernte Leistung je Leistungsschritt, Startwert (Pmax − Pmin) / (2 × Zahl der Geräte) (FR-LOAD-02). Gespeichert im selben `Store` unter `load`.

Anzeigeversatz (FR-SOC-04): Diagnose-Sensoren `display_offset` und `largest_deviation` (Einheit K, nur lesbar; `largest_deviation` ist unbekannt, solange keine Abweichung gemessen ist). Die Parameter `display_offset_k` (3,5), `offset_threshold_pct` (10), `offset_target_pct` (5) und `offset_cap_factor` (1,25) stehen in der Optionengruppe „SOC“.

Gelernte Kapazität (FR-PLNR-02/03): Diagnose-Sensoren `learned_heat_capacity` und `learned_cool_capacity` (kWh/K, nur lesbar),
Attribute `estimates`, `updated`, `last_estimate` und `pending_estimates` (Einzelschätzungen in kWh/K). Speicherung im `Store` (`climate_control.<entry_id>.learned`), siehe `50-capacity-learning.md`.

## Dienst

`climate_control.run_cycle` – führt sofort einen Zyklus aus; optional `config_entry_id` für eine Anlage.

`climate_control.reset_learned_capacity` – setzt die gelernten Kapazitäten auf den Startwert zurück (FR-PLNR-03); optional
`config_entry_id`. Nur über die Entwicklerwerkzeuge erreichbar, nirgends in der Oberfläche angeboten.

`climate_control.set_display_offset` – setzt den Anzeigeversatz von Hand (FR-SOC-05); Pflichtfeld `value` (≥ 0, im Dienstformular mit 3,5 vorbelegt), optional `config_entry_id`.

`climate_control.set_largest_deviation` – setzt die größte gemessene Abweichung von Hand (FR-SOC-05); `value` leer = noch nicht gemessen (der Versatz wird dann nicht angepasst), optional `config_entry_id`. Beide Dienste speichern sofort und rechnen einen Zyklus, damit die Diagnosewerte den neuen Wert zeigen.

## Aufzeichnung (FR-OBS-01)

Datei `<Konfigurationsordner>/climate_control/<entry_id>.jsonl` (JSON-Zeilen, Ereignisse `plant` mit u. a. `expected_w` und `unit`, `power` mit `power_w` bei Änderung ab 20 W, `command` mit `unit`, `mode`, `target_c`, `steps` bei Änderung des Befehls der Regelung), Aufbau siehe
`10-architecture.md`.

## Geräte

Aufrufe `climate.set_hvac_mode` und `climate.set_temperature` (blocking). Gelesen werden Zustand (Modus),
`current_temperature` und `temperature`.

## Benennung und Migration

- Anzeigenamen der Sensoren, die HAEO-Felder befüllen, sind die Feldnamen von HAEO 0.4.1 (alle Sprachen gleich,
  HAEO ist nur englisch): Capacity, State of Charge, Min/Max Charge Level, Undercharge/Overcharge percentage,
  Undercharge/Overcharge cost, Charge efficiency, Max discharge power, Charge cost (Batteriefeld),
  Max Power Source to Target (Verbindung). Felder im Einrichtungsdialog nennen das HAEO-Feld nach „→“.
- `unique_id` (Schlüssel) und bereits registrierte Entitäts-IDs bleiben bei Umbenennungen unverändert;
  nur der Anzeigename folgt der Übersetzung. Auswahlen in HAEO bleiben dadurch gültig.
- Config-Entry-Version 2 (`async_migrate_entry`): entfernt `stage1_w` und `capacity_kwh_per_k` aus den Daten,
  verschiebt `comfort_max_c`/`overload_max_c` aus den Optionen in jedes Innengerät (eigene Werte haben Vorrang),
  entfernt `power_class` aus den Innengeräten.
- Config-Entry-Version 4: `comfort_max_c`/`overload_max_c` der Innengeräte und `soc_min_c`, `soc_max_c`, `hard_min_below_k` der Optionen
  entfallen (FR-BAND-01, relative SOC-Skala); es gelten die Standardwerte (Regelbereich 2, absolute Grenze 3), alte absolute
  Werte werden nicht umgerechnet.
- Config-Entry-Version 3: Fensterkontakte eines Innengeräts werden als Liste gespeichert (vor 0.3 ein einzelner
  Text). Eine Mehrfachauswahl braucht eine Liste als Vorgabewert, sonst lässt sich das Feld im Dialog nicht mehr
  ändern; das Formular wandelt zusätzlich einen noch gespeicherten Einzelwert um.
