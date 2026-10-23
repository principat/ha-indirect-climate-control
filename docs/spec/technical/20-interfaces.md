# 20 Schnittstellen

## Konfiguration (FR-GEN-01, FR-CFG-01..03)

| Ebene | Ablauf | Gespeichert in |
| --- | --- | --- |
| Anlage | Config Flow `user`, änderbar über `reconfigure`: Name, Pmin, Pmax, Planer-Sensor(en) optional | `entry.data`, Titel |
| Innengerät | Subentry-Typ `room` („Innengerät hinzufügen" im Drei-Punkte-Menü des Eintrags), je Gerät einzeln anlegen, ändern (`reconfigure`), löschen: Klima-Entität, Name, Sollwert (fest), optional Sollwert-Entität (`input_number`, `number`, `sensor`; gilt vor dem festen Wert, wenn 5–30 °C), Obergrenze ohne Aufschlag, Überlastgrenze, Nennleistung (bestimmt die Leistungsklasse), Fläche, Fensterkontakte (mehrere, offen = einer offen) | `entry.subentries`, `unique_id` = Klima-Entität (je Anlage nur einmal) |
| Parameter | Options Flow: Menü mit Gruppen `control`, `soc`, `safety`, `planner` (`help.PARAMETER_GROUPS`); jede Gruppe speichert zusammen mit den übrigen Werten | `entry.options` |
| Hilfeschalter | `help_expanded` | `entry.options` |

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
Klima (`sensor.klima_power_source_target`), bei zwei HAEO-Verbindungen beide. Nicht die
Ladeleistung der Batterie: Am Knoten Klima hängt auch die Last Wärmebedarf, die HAEO direkt versorgen kann
(Topologie in `README.md`). Mehrere Sensoren werden je Zeitpunkt addiert
(`core.plan.combine`); der Summenplan ist so alt wie sein ältester Teil und endet mit dem kürzesten.
Fällt ein Sensor aus, gilt der Plan als fehlend. Zielbild der HAEO-Topologie: `README.md`.

- Zustand: Leistung jetzt, Einheit aus `unit_of_measurement` (`kW` → ×1000, sonst W).
- Attribut `forecast`: Liste von `{time|start_time, value}` oder Abbildung Zeit → Wert. Zeiten ISO 8601,
  ohne Zeitzone = Zeitzone des Empfangs.
- Ohne `forecast` gilt der Zustand allein als Plan ab Empfang.
- Empfangszeit = max(`last_updated`, `last_reported`).
- `unavailable`/`unknown` = Planer ausgefallen → Rückfall.

Ungeprüfte Annahme: Das Ausgabeformat von HAEO-Sensoren entspricht dieser Form. Belegt ist nur, dass HAEO
Eingänge mit `forecast: [{time, value}]` liest (haeo.io, Stand 21.10.2026).

### Ausgang: Vorgaben für den Planer (FR-PLNR-01)

Sensoren je Anlage, Prognosen im Attribut `forecast: [{time, value}]` (stündlich, `planner_horizon_h`).

| Sensor (Schlüssel) | Einheit | Bedeutung, Zuordnung HAEO-Batterie |
| --- | --- | --- |
| `soc` | % | Current Charge Percentage, Attribut `worst_room` |
| `capacity` | kWh | Capacity = Kapazität je K (Startwert 7) × Skalenbreite |
| `min_charge` | % | Min Charge Percentage (flächengewichteter Sollwert, nachts abgesenkt), mit Prognose |
| `undercharge` | % | Undercharge Percentage (hartes Minimum, nachts abgesenkt), mit Prognose |
| `max_charge` | % | Max Charge Percentage (Obergrenze ohne Aufschlag) |
| `overcharge` | % | Overcharge Percentage (Überlastgrenze) |
| `undercharge_cost` / `overcharge_cost` | Währung/kWh | Undercharge/Overcharge Cost |
| `efficiency` | % | Charge/Discharge efficiency |
| `max_discharge_power` | kW | Max Discharge Power |
| `max_charge_power` | kW | Max Power der einen Verbindung Haus → Klima (Grundvariante, = Pmax) |
| `charge_cost` | Währung/kWh | Aufschlag Spätladen, mit fallender Prognose |

### Status

`planned_power` (W, Prognose), `requested_power` (W, Attribut `served_rooms`), `binary_sensor` `running`, `fallback`.

Je Innengerät ein eigenes Gerät (Subentry), Diagnose-Sensoren `room_deviation` (K), `room_heat_demand` (kWh),
`room_storage` (kWh), `entity_category: diagnostic` (FR-OBS-02).

## Dienst

`climate_control.run_cycle` – führt sofort einen Zyklus aus; optional `config_entry_id` für eine Anlage.

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
