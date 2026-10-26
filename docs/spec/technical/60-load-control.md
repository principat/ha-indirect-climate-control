# 60 Lastregelung: Dauerbetrieb der bedienten Räume

Status: **umgesetzt am 26.10.2026** (`core/serving.py`, `core/load.py`, Anbindung in `controller.py` und `coordinator.py`). Grundlage
sind FR-LOAD-01, FR-LOAD-02, FR-LOAD-05 bis FR-LOAD-08 und FR-SRC-02 sowie die Messungen vom 26.10.2026 (`docs/environment/devices-lg-multi-v.md`).
Das Konzept ersetzt den Wechselbetrieb mit Bahnen und Übergabe (bis Version 0.12.0). Es ist an Messwerten noch nicht im Betrieb geprüft.

## Warum der Wechselbetrieb entfiel

Messungen am 26.10.2026 zeigten: Das Außengerät hat nach einem Stopp eine Sperrzeit von etwa 4 Minuten, ein Innengerät braucht Minuten bis
zur vollen Leistung (Spitze nach 3 bis 4 Minuten), und der Verdichter stoppt innerhalb von Sekunden, wenn das tragende Gerät in den neutralen
Modus geht, solange der Nachfolger noch nicht trägt. Ein Wechsel alle zwei Minuten gab dem Außengerät nie Zeit, Last aufzubauen, und die Übergabe
löste den Stopp aus. Die Geräte regeln sich außerdem selbst ab (Sollwert plus etwa 3,5 K).

## Mechanismus

1. **Sollwert.** Ein bedientes Gerät erhält den Sollwert seines Raums, ohne Puffer (`Command(main_mode, r.setpoint_c)`). Die Geräte heizen
   über den Sollwert hinaus und regeln sich bei etwa 3,5 K darüber selbst ab (zwei Geräte, Keller und Marcel). Der Sollwert beeinflusst den
   Verlauf der Außenleistung nicht (Wohnzimmer, 19,5 bis 28 °C, gleich).
2. **Dauerbetrieb** (`core/serving.py`). Ein bedienter Raum (`Served`: Raum, Beginn, Anzeige bei Beginn, aktiv, niedrigste Leistung seit
   Beginn) bleibt bedient, bis seine Livewert-Anzeige `cutoff_k` (3,5) über dem Sollwert liegt (im Kühlen gespiegelt). Der Abschaltabstand ersetzt
   für bediente Räume die Überlastgrenze. Räume, deren Livewert den Abschaltabstand schon erreicht hat, sind nicht mehr zulässig
   (`controller.py`, `eligible`). Die Rangfolge (`rank`, 1e-9 als Band) bleibt: größte Abweichung zuerst, bei genau gleicher Abweichung die
   Leistungsklasse, Räume über dem Sollwert (Puffer) kommen danach.
3. **Weitere Räume** (immer nur einer, nie, solange ein bedienter Raum noch nicht aktiv ist). Ein Raum wird zugeschaltet, wenn
   - kein Raum bedient ist,
   - die gemessene Leistung (Mittel der letzten drei Zyklen) nach der Anlaufphase um mehr als `max(Totband, p̄ / 2)` unter der Anforderung liegt
     (`p̄`: erwartete Leistung eines weiteren Raums; so pendelt die Zahl nicht zwischen zwei Stufen), oder
   - alle bedienten Räume den Zuschaltabstand `cutoff_k − join_margin_k` (2,5) erreicht haben oder abgeregelt sind.
   Die Zahl ist durch Pmax begrenzt: `1 + round((Pmax − Pmin) / p̄)` (`load.py: _max_rooms`).
4. **Aktiv.** Ein zugeschalteter Raum gilt als aktiv, wenn seine Livewert-Anzeige seit dem Start um `activation_rise_k` (1) gestiegen ist,
   spätestens nach `load_settle_max_s` (10 min) oder wenn kein Messwert vorliegt.
5. **Abgabe.** Ein Raum am Abschaltabstand geht in den neutralen Modus, wenn mindestens zwei andere aktiv sind, oder wenn genau ein anderer aktiv
   ist und die Leistung seit dessen Start wieder gestiegen ist (Mittel > niedrigste Leistung seit dessen Start + Totband), oder wenn weder ein
   anderer Raum bedient noch einer zulässig ist. Ist kein anderer aktiv, wartet der Raum auf den Nachfolger, der nach 3. sofort startet.
6. **Überschuss.** Liegt die Leistung nach der Anlaufphase um mehr als `max(Totband, p̄ / 2)` über der Anforderung und sind mindestens zwei Räume
   bedient und aktiv, gibt der Raum mit dem größten Abstand über dem Sollwert ab (FR-LOAD-07).
7. **Anlaufphase** (`startup_s`, 600 s) zählt ab dem Start der Anlage und ab jeder Änderung (Zuschalten oder Abgabe) und gilt für das Zuschalten nach der
   Leistung und für den Überschuss, nicht für das Zuschalten nach der Temperatur und nicht für die Abgabe am Abschaltabstand.
8. **Zurücksetzen** beim Stopp der Anlage und beim Wechsel der Betriebsart.

## Einfrieren der Gerätetemperaturen (FR-SRC-02)

`Controller._assess`. Sobald ein Gerät auf Heizen oder Kühlen gestellt ist (befohlen im letzten Zyklus oder gemeldet), gelten für Rangfolge, SOC,
Überhitzungsregel und Schutz die zuletzt eingeschwungenen Werte (`_frozen`, aus `_assessed` des Zyklus davor). Das Einfrieren endet, wenn kein Gerät
mehr arbeitet und `settle_s` (600 s) seit dem ersten ruhigen Zyklus vergangen sind (`_calm_since`). `settle_s = 0` schaltet das Einfrieren aus
(die e2e-Tests nutzen das). Die Livewerte (`live`) gehen nur an den Dauerbetrieb: Abschaltabstand, Zuschaltabstand und Aktivierung. Die Prüfung auf
Unterkühlung (FR-SAFE-02) arbeitet mit den eingefrorenen Werten und kann daher erst nach dem Einschwingen einen neuen Raum finden.

## Lernen der Leistung je Gerät (FR-LOAD-02)

Unverändert: Nach einer Änderung der Zahl der bedienten Geräte wird die Außenleistung beobachtet, bis sie beruhigt ist (Mittel der letzten drei
Zyklen innerhalb des Totbands, Höchstzeit `load_settle_max_s`, die sich der Anlage anpasst). Die gemessene Änderung geteilt durch die erwartete
bestimmt einen Faktor für die beteiligten Geräte. Ein Lauf aus dem Stillstand lehrt nichts. Beobachtungen, in die anderes hineinspielt, werden
verworfen. Durch die Anlaufphase von 10 Minuten zwischen zwei Änderungen ist das Lernen jetzt häufiger möglich als im Wechselbetrieb.

## Beruhigung der Außenleistung

1. Die Leistung wird je Regelzyklus gemittelt (`cycle_s`, Standard 60 s).
2. Toleranz ist das Totband (10 % von Pmin). Beruhigt heißt: die letzten drei Mittelwerte liegen höchstens ein Totband auseinander.
3. Höchstzeit: sonst wird die Beobachtung verworfen. Sie passt sich an (das Dreifache der beobachteten mittleren Beruhigungszeit, höchstens der
   Parameter, mindestens drei Zyklen).
4. Dauerhaft schwankende Leistung beruhigt sich nicht, das Lernen pausiert dann von selbst.

## Offen (Annahmen, bis zur Prüfung im Betrieb)

1. **Abschaltabstand 3,5:** an zwei Geräten gemessen (zwischen 3,5 und 4), die Anzeige ändert sich nur alle 5 Minuten in 0,5-K-Schritten. Andere
   Geräte sind nicht gemessen, das soll der Anlernmodus (FR-LRN-01, Vorschlag) leisten.
2. **Abgabe bei einem anderen aktiven Raum:** nach der Leistung (steigend), an einem Fall gemessen. Ob die Anlage bei der Abgabe weiterläuft, hängt am
   Nachfolger, der nach den Messungen mindestens zehn Minuten lief.
3. **Zuschalten nach Temperatur:** Zuschaltabstand 2,5 und Aktivierungsanstieg 1 sind Vorgaben des Nutzers, die an einem Lauf mit zwei Geräten (Keller, Marcel)
   erprobt sind.
4. **Wiederanlauf nach dem Selbstabschalten:** Hysterese nicht gemessen. Die Sperrzeit von etwa 4 Minuten ist nur beobachtet, die Regelung nutzt sie nicht.
5. **Überlastgrenze bedienter Räume:** Für bediente Räume gilt der Abschaltabstand statt der Überlastgrenze (Standard 3). Der Nutzer will noch prüfen, ob
   die Überhitzungs- und Überlastgrenze nur im neutralen Modus berücksichtigt werden sollen (offener Punkt der Fachspec).
6. **Kühlbetrieb:** alles gespiegelt angenommen, nicht gemessen.
7. **Messwert der Leistung fehlt:** Ohne Messwert der Außenleistung startet nur der erste Raum und die Räume werden über den Abschaltabstand und
   die Temperatur zugeschaltet. Die Messung ist Pflicht (FR-GEN-01), der Fall tritt nur beim Ausfall des Sensors auf.
