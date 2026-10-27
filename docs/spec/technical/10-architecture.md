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
| `distribution.py` | FR-DIST-01, FR-DIST-02 | Rangstufen nach Abweichung mit Gleichstand-Band, Gruppen je Leistungsklasse (= gleiche Nennleistung, kein eigenes Feld); die Stufen gehen an `core/load.py` |
| `serving.py` | FR-LOAD-05 bis FR-LOAD-08 | bediente Räume im Dauerbetrieb: Abschaltabstand am Livewert, Zuschalten nach Leistung und Temperatur, Aktivierung, Abgabe, Überschuss |
| `diagnostics.py` | FR-OBS-02 | Abweichung, Wärmebedarf und Speicherkapazität je Raum aus den im Zyklus verwendeten Temperaturen |
| `modes.py` | FR-MODE-01 | nächster zulässiger Moduszustand (Heizen/Kühlen nur über neutral) |
| `planner_model.py` | FR-PLNR-01 | Vorgaben für den Planer inkl. Stundenprognosen |
| `controller.py` | alle obigen, FR-PLAN-04, FR-SAFE-01..04, FR-MODE-03, FR-SRC-01 | ein Regelzyklus |

## Datenfluss je Zyklus (`Controller.step`)

0. Temperatureinheit (FR-UNIT-01): Der Kern kennt keine Einheit. Er arbeitet nur mit Differenzen von Temperaturen und Sollwerten
   und läuft deshalb in der Einheit der Anlage, ohne Umrechnung. Abstände (Regelbereich, Grenzen, Skala, Offset, Band, Schwellen)
   sind Zahlen in dieser Einheit, die Startwerte bleiben gleich. Die Einheit zählt nur bei absoluten Werten im Adapter: Vorgabe und
   Bereich des Sollwerts (`core/units.py`: 5–30 °C bzw. 41–86 °F, Plausibilität der Sollwert-Entität) und die Beschriftung der Felder.
0. Betriebsart `season` (FR-SEAS-01): Schalter an = Kühlen, sonst Heizen (auch ohne Schalter oder bei `unavailable`).
   `Season.sign` (+1 Heizen, −1 Kühlen) spiegelt Abweichung, SOC, Grenzen und Schutz; ein Wechsel setzt Glättung, Lauf und
   Zeitgeber zurück. Im Kühlen tauschen die Seiten (`RoomConfig.discharge_band/charge_band/discharge_limit/charge_limit(season)`):
   Entladen heißt dann wärmer als der Sollwert.
1. Gerätetemperatur je Raum lesen, unverändert (0,5-K-Schritte) übernehmen, Ausreißerfilter (FR-SRC-01, FR-SOC-02).
2. Aktive Räume = Temperatur und Modus bekannt, Fenster zu.
3. SOC (FR-SOC-01, `core/soc.py`): je aktivem Raum `room_fill` (Füllstand 0 bis 1 von unterem Randbereich, Wohlfühlbereich und oberem
   Randbereich aus Abstand zum aktuellen Sollwert, Regelbereich und absoluter Grenze; Sollwert genau bei 0,5 des Wohlfühlbereichs, jede
   Seite mit eigener Steigung; Randbereich ohne Breite = Stufe an der Kante), dann `soc_of`: 10 % · Mittel der unteren Füllstände +
   80 % · gewichtetes Mittel der Wohlfühl-Füllstände (Gewicht `exp(−f² / 2σ²)` mit `σ = soc_sigma`, Standard 0,3, relativ zum kältesten
   Raum gerechnet, damit eine schmale Glocke nicht auf 0 unterläuft) + 10 % · Mittel der oberen Füllstände; Median über 15 min.
   Beim Kühlen sind die Seiten über `Season.sign` gespiegelt. Das Attribut `worst_room` bleibt: der Raum mit der größten Abweichung.
4. Überhitzungs-Zeitgeber je Raum führen.
5. Plan fehlt oder veraltet → zuerst Warten (`fallback_delay_s`, 600 s): Geräte unverändert, Schutz gilt. Danach Rückfall:
   schrittweise (`fallback_step_s`, 120 s) je eine Gruppe gleicher Nennleistung auf Heizen mit Standard-Sollwert,
   größte Abweichung zuerst; laufende Geräte bleiben an. Kommt der Plan zurück, beginnt beim nächsten Ausfall
   die Wartezeit von vorn. Absolute Grenze unten und Überhitzung gelten in jedem Zweig, Fenster überschreiben alles.
   Sonst: Schwellenentscheidung mit Hysterese und Mindestlaufzeit der Anlage (`min_run_s`, 600 s ab jedem Start, Halten
   mit mindestens Pmin, nur solange ein Raum unter seiner absoluten Grenze auf der Ladeseite liegt, Zeitgeber nur bei Aus → An neu, keine Mindestpause), bei Betrieb Räume auswählen (Ziel = Gerätetemperatur + Heiz-Offset,
   höchstens Sollwert + absolute Grenze), übrige neutral; absolute Grenze unten überschritten → Heizen; Überhitzung ≥ Dauer und kein Heizziel → Kühlen.
6. Offenes Fenster → neutral (überschreibt alles, auch den Rückfall).
7. `next_modes` gegen die aktuellen Modi: bei Konflikt zuerst alle nicht neutralen Geräte neutral.
8. Befehle nur für Heizen/Kühlen mit Sollwert.

Lernen (FR-PLNR-02, `core/learning.py`): Der Adapter füttert `CapacityLearner.update` je Zyklus mit den *rohen* Gerätetemperaturen
(0,5-K-Schritte, nicht den gerundeten), dem Leistungssensor des Außengeräts (W oder kW) und `running`. Speicherung im `Store`
(`climate_control.<entry_id>.learned`, verzögert 60 s, beim Entladen sofort wenn geändert). Die gelernte Kapazität der
aktuellen Betriebsart geht in `planner_inputs` und die Diagnose ein. Dienst `reset_learned_capacity` (FR-PLNR-03) setzt zurück.

Der Adapter (`coordinator.py`) führt den Zyklus im Intervall `cycle_s` aus, wendet nur Änderungen an und
setzt nach jedem Wechsel auf Heizen/Kühlen den Sollwert erneut (FR-MODE-02). Weicht der Sollwert des Geräts
später ab (z. B. verspätet übernommener gemerkter Wert), korrigiert der nächste Zyklus ihn.

## Annahmen (nicht in der Fachspec festgelegt, als Parameter konfigurierbar)

| Thema | Umsetzung | Parameter |
| --- | --- | --- |
| SOC relativ zum Sollwert | je Raum eigene Skala (Randbereiche 10 % / Wohlfühlbereich 80 % / Randbereiche 10 %, Sollwert = 50 %), Anlagen-SOC aus Mittel der Ränder und mit Halbglocke gewichtetem Mittel des Wohlfühlbereichs | `soc_sigma` (0,3) |
| Gleichstand „innerhalb des Bandes" | Differenz zur größten Abweichung der Stufe < Band | `tie_band_k` |
| Last (FR-LOAD-01/02/05/06/07/08) | Lastregelung `core/load.py`: erwartete Last = Pmin + gelernte Leistung je weiterem Gerät, Totband, höchstens so viele Räume wie Pmax erlaubt; Dauerbetrieb `core/serving.py` (siehe 60-load-control.md); Sollwert = Sollwert des Raums, ohne Puffer; Einfrieren der Gerätetemperaturen im Controller (FR-SRC-02); Lernen je Innengerät nach Beruhigung der Außenleistung | `step` je Innengerät (nur zur Information), `load_deadband_ratio`, `load_settle_max_s`, `cutoff_k`, `join_margin_k`, `activation_rise_k`, `startup_s`, `settle_s` |
| Ausreißer | einmal verworfen, bei Bestätigung im nächsten Zyklus übernommen | `outlier_k` |
| Fenster offen | Gerät neutral, nicht im SOC, nicht verteilt, auch im Rückfall | – |
| Plan veraltet | älter als `plan_max_age_s` (1800 s) oder Zeitpunkt außerhalb der Prognose | `plan_max_age_s` |
| Nachtabsenkung | senkt Untergrenze und absolute Grenze unten für den Planer um 1; Raumschutz unverändert | `night_setback_k` |
| Regelbereich, absolute Grenze (FR-BAND-01) | je Innengerät, Abstand zum aktuellen Sollwert (Standard 2 / 3, unten und oben); für den Planer flächengewichtet; Schutz nutzt die Grenze des Raums | `band_down/up`, `limit_down/up` je Innengerät |
| Aufschlag Überlast | 0,003 je kWh | `overcharge_cost` |
| Pufferkapazität | Startwert 3 kWh/K, keine Einstellung; Lernen siehe 50-capacity-learning.md (Konzept) | – |
| Aufschlag Spätladen „fällt mit der Zeit" | linear vom Startwert auf 0 über den Horizont, damit bei gleichem Preis später geladen wird | `late_charge_surcharge` |
| Gewichtung Untergrenzen | Fläche der Räume | Fläche je Innengerät |
| Kapazität je Raum (Diagnose) | Pufferkapazität nach Fläche auf die Räume verteilt | Fläche je Innengerät |

Alle beschlossenen Anforderungen sind umgesetzt.

## Aufzeichnung (FR-OBS-01)

`core/journal.py` vergleicht je Zyklus den Zustand (Anlage läuft, Modus, Gerätetemperatur, Sollwert, Lüfterstufe je Innengerät)
mit dem letzten und liefert nur Änderungen als Einträge: `plant` bei Start/Stopp (mit SOC, geplanter und angeforderter Leistung,
Betriebsart, Rückfall) `power` bei einer Änderung der Außenleistung um mindestens 20 W seit dem letzten Eintrag (`POWER_STEP_W`, Mittel der letzten zwei Messwerte) `command` je geändertem Befehl der Regelung (Modus, Sollwert, Schritte; steht vor den `unit`-Einträgen desselben Zyklus) und `unit` je geändertem Gerät. Der `unit`-Eintrag zeigt den Zustand, den das Gerät unmittelbar nach dem Befehl meldet; er kann dem Befehl nachlaufen (Beobachtung: der gemerkte Sollwert 24 °C steht dort oft einen Zyklus lang). Der erste Zyklus schreibt den Ausgangszustand. `record_file.py` hängt die
Einträge als JSON-Zeilen an `<Konfigurationsordner>/climate_control/<entry_id>.jsonl` an (Executor, seltene Schreibzugriffe wegen
der SD-Karte) und ersetzt bei mehr als 1 MB die Vorgängerdatei `.jsonl.1`, es bleiben also höchstens etwa 2 MB. Der Recorder von
Home Assistant bleibt unberührt, die Datei ergänzt ihn um Lüfterstufe und die Gründe der Anlage.
