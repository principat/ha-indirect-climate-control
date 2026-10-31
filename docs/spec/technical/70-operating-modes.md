# 70 Betriebsmodi, Heizoffset, Lüfterstufe

Abgeleitet aus FR-OFS-01, FR-FAN-01, FR-OPM-01 bis FR-OPM-06. Ungeprüfte Annahmen sind als solche gekennzeichnet.

## Umschaltung (FR-OPM-01)

- `core.model.OperatingMode`: `hems_optimized` (Standard), `hems_buffer`, `manufacturer`, `manufacturer_cycle`.
- Wahl: `select`-Entität `operating_mode` je Anlage (`select.py`, Schlüssel `operating_mode`, Übersetzungen unter
  `entity.select`). Der Koordinator hält den Wert (`operating_mode`), speichert ihn im `Store` der Anlage
  (Schlüssel `operating_mode` neben den gelernten Werten) und führt nach der Wahl sofort einen Zyklus aus.
  Ein unbekannter gespeicherter Wert wird mit einer Warnung ignoriert.
- `Controller.step(..., operating, local_now)`: Bei einem Wechsel setzt `_change_operating` den Zustand zurück
  (Lauf, Lastregler, Glättung, gemerkte Werte, Halten). Danach verzweigt `step` nach der Berechnung der
  Messwerte: `_manufacturer` (beide Herstellermodi), `_buffer`, sonst der bisherige Ablauf.
- `local_now`: Ortszeit für die Nachtabsenkung (`planner_model.is_night`), der Koordinator übergibt `dt_util.as_local`.
- Alle Modi: Fenster offen → neutraler Modus (FR-SAFE-01). Moduswechsel über `modes.next_modes` (FR-MODE-01).
- Ohne Planer-Sensor (Inbetriebnahme) gehen in keinem Modus Befehle an die Geräte.

## Heizoffset (FR-OFS-01)

`Parameters.heat_offset_k` (Gruppe `soc`, Startwert 2). `Controller.step` bildet nach dem Ausreißerfilter
`shifted = gemeldet − heat_offset_k` (nur Heizen, Kühlen: 0). `shifted` geht in `_assess`, den Anker,
SOC, Rangfolge, Schutz, Überhitzung und in die Modi Hersteller und Puffer; der Lastregler (Abschaltabstand,
Zuschaltabstand, Aktivierungsanstieg, Überlastprüfung des bedienten Geräts) liest weiter `live`. Der Sollwert am
Gerät wird nie um den Offset angehoben, deshalb gibt es keine Rückrechnung beim Wechsel auf die Herstellersteuerung.
Folge: Die größte gemessene Abweichung (FR-SOC-04) ist die des abgezogenen Werts.

Die Tests setzen den Offset in `tests/unit/helpers.py` und `tests/integration/conftest.py` auf 0, soweit sie den
Offset nicht selbst prüfen; der e2e-Test setzt ihn ebenfalls auf 0.

## Herstellersteuerung (FR-OPM-02) und Taktoptimierung (FR-OPM-03)

- Befehl je Gerät: Modus der Betriebsart, Sollwert = `setpoint_c` abzüglich `sign · night_setback_k` in der Nacht.
  Kein Plan, kein Lastregler, kein Rückfall, keine Lüfterstufe (`Command.boost` False).
- `planner_inputs(..., MANUFACTURER)`: `capacity_kwh = 0`. **Ungeprüfte Annahme:** Der Planer (HAEO) akzeptiert eine
  Kapazität von 0 und behandelt die Batterie dann als nicht nutzbar. Alle übrigen Werte bleiben.
- SOC wird weiter berechnet (Formel von FR-SOC-01 ohne Anker aus `shifted`, geglättet), damit der Sensor gültig bleibt.
- Standby (`Controller._standby`): gemessene Leistung (Mittel der letzten zwei Messungen) unter
  `stop_ratio · p_min_w` seit mindestens `standby_delay_s` (Startwert 300 s). Ohne Messwert nie Standby.
- Taktoptimierung: im Standby Sollwert `− sign · cycle_setback_k` (Startwert 1). **Ungeprüfte Annahme:**
  Die Anlage startet dann seltener; Höhe und Verzögerung sind Schätzwerte.

## HEMS-Optimiert (FR-OPM-04)

Bisheriger Ablauf. Neu: `Controller._plant_stopped` hält den Zeitpunkt, an dem `running` von wahr auf falsch
wechselt, `CycleResult.cooldown_left_s = max(0, cooldown_s − Zeit seit Stopp)` (Startwert 3600 s); ein neuer Lauf
löscht den Zeitpunkt. `planner_inputs(..., cooldown_left_s)` addiert `cooldown_surcharge` (Startwert 0,001) zu jedem
stündlichen Zeitfenster der Ladekosten (`charge_cost`, Prognose), das den Zeitraum `[jetzt, jetzt + Rest)` schneidet.

## HEMS-Puffersteuerung (FR-OPM-05, FR-OPM-06)

Modul `core/buffer.py`, Ablauf `Controller._buffer`:

1. SOC = `buffer_soc`: Skala je Raum = `night_setback_k + band_up`, gespeichert =
   `min(Skala, max(0, sign·(T − (Sollwert − sign·night_setback_k))))`; Summe der gespeicherten Anteile geteilt durch
   die Summe der Skalen, mal 100, geglättet (Median über `soc_smoothing_s`). `T` ist `shifted`, kein Anker, kein Halten
   („nachgeführt über die Isttemperatur").
2. Plan: ohne gültigen Plan keine Anforderung, kein Rückfall. Sonst `threshold.decide` (Start 80 %, Halten 50 % von Pmin),
   ohne Mindestlaufzeit, denn die Anlage läuft ohnehin unter der Herstellersteuerung.
3. Schritte: `room_steps = max(1, round(band_up / step))` je Raum (`step` = Meldeschritt, Startwert 0,5); gesamt
   `N = Σ room_steps`; `power_steps = min(N, max(1, round(angefordert / (Pmax / N))))`.
4. Verteilung: `allocate` reihum, ein Schritt je Raum, Kapazität 0 für Räume, deren Puffer voll ist
   (`stored_k ≥ band_up`). Beginn der Reihenfolge: `_rotation`, rückt mit jedem neuen Ladeabschnitt (0 → größer 0
   Schritte) um einen Raum weiter.
5. Befehl: Heizen/Kühlen mit `Komfortsollwert + sign · Schritte · step`, begrenzt auf `Sollwert + sign · band_up`.
   Komfortsollwert = Sollwert, nachts um die Absenkung verändert (die Absenkung ist Teil der Skala).
6. Planer: `planner_inputs(..., HEMS_BUFFER)`: Skala 0 % (abgesenkter Sollwert) bis 100 % (Obergrenze des
   Pufferbereichs). `min_charge = undercharge` = `100 · night_setback_k / (night_setback_k + mittlerer band_up)`
   tagsüber (Beispiel 33 %), 0 % in den Nachtstunden (Prognose je Stunde); `max_charge = overcharge = 100`;
   Kapazität = `capacity_kwh_per_k · (night_setback_k + mittlerer band_up)`.
   **Ungeprüfte Annahme:** Das ist eine brauchbare Abbildung für HAEO; die gelernte Kapazität (Joule je 0,1 K) stammt aus
   dem Modus HEMS-Optimiert und wird hier unverändert verwendet.
7. `CycleResult.steps` enthält die Schritte je Raum, die Diagnose `room_offset` zeigt damit die Anhebung des Sollwerts.

Keine Schutzregeln FR-SAFE-02/03 in den Modi Hersteller und Puffer: Die Geräte halten den Komfort selbst.

## Lüfterstufe (FR-FAN-01)

- Je Innengerät optional `fan_heat`, `fan_neutral` (Textfelder, Namen der Lüfterstufen wie das Gerät sie meldet).
- `Controller._resolve` setzt `Command.boost` nur für Heizen in HEMS-Optimiert und HEMS-Puffersteuerung
  (`boost` nimmt an der Gleichheit von `Command` nicht teil).
- `Coordinator._apply_fan`: bei `boost` und `fan_heat` die Stufe merken (`_fan_before`) und setzen
  (`climate.set_fan_mode`); sonst, wenn eine Stufe gemerkt ist, auf `fan_neutral` oder die gemerkte Stufe zurücksetzen.
  Gemerkt wird nur im Speicher: Nach einem Neustart während des Heizens bleibt die Stufe erhöht, bis der Nutzer sie ändert
  (ungeprüfte Annahme, dass das hinnehmbar ist).
