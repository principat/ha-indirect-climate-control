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
   - ein bedienter Raum den Zuschaltabstand `cutoff_k − join_margin_k` (2,5) erreicht hat und noch keinen Ersatz hat: Der zugeschaltete Raum
     ist sein Ersatz (`Served.replaces`).
   Die Zahl ist durch Pmax begrenzt: `1 + round((Pmax − Pmin) / p̄)` (`load.py: _max_rooms`). Ein Raum am Abschaltabstand zählt dabei
   nicht mit (`serving.py: room_count`), sonst könnte sein Ersatz nie starten.
4. **Aktiv.** Ein zugeschalteter Raum gilt als aktiv, wenn seine Livewert-Anzeige seit dem Start um `activation_rise_k` (1) gestiegen ist,
   spätestens nach `load_settle_max_s` (10 min) oder wenn kein Messwert vorliegt.
5. **Abgabe.** Ein Raum am Abschaltabstand geht in den neutralen Modus erst, wenn sein Ersatz aktiv ist, auch bei mehreren bedienten Räumen.
   Hat er keinen Ersatz, wird einer gestartet (3.). Er geht sofort, wenn niemand ihn ersetzen kann: kein weiterer Raum ist zulässig, oder die
   Höchstzahl der arbeitenden Räume ist erreicht. Die frühere Regel über die steigende Leistung (`floor_w`) entfiel, die Aktivierung des Ersatzes
   ersetzt sie.
6. **Überschuss.** Liegt die Leistung nach der Anlaufphase um mehr als `max(Totband, p̄ / 2)` über der Anforderung und sind mindestens zwei Räume
   bedient und aktiv, gibt der Raum mit dem größten Abstand über dem Sollwert ab (FR-LOAD-07).
7. **Anlaufphase** (`startup_s`, 600 s) zählt ab dem Start der Anlage und ab jeder Änderung (Zuschalten oder Abgabe) und gilt für das Zuschalten nach der
   Leistung und für den Überschuss, nicht für das Zuschalten nach der Temperatur und nicht für die Abgabe am Abschaltabstand.
8. **Zurücksetzen** beim Stopp der Anlage und beim Wechsel der Betriebsart.

## Halten und Absinken der Gerätetemperaturen (FR-SRC-02)

`Controller._assess`. Arbeitet irgendein Gerät (Heizen oder Kühlen, befohlen im letzten Zyklus oder gemeldet) oder liegt der Stopp des letzten
weniger als `settle_s` (600 s) zurück (`_last_busy`), gilt für Rangfolge, SOC, Überhitzungsregel und Schutz: Ein arbeitendes Gerät behält seinen
zuletzt bewerteten Wert (`_assessed`), jedes andere nimmt `min(bewerteter, gemeldeter Wert)`, eine steigende Anzeige zählt nicht (das beheizte Gerät
schmarotzt über die Leitungen auch auf die neutralen Geräte). Ein Gerät, das gerade gestoppt hat (`_working` im Zyklus davor), übernimmt seinen
gemeldeten Wert einmal, danach gilt wieder nur das Absinken. Nach `settle_s` ohne arbeitendes Gerät zählen alle gemeldeten Werte. `settle_s = 0`
schaltet das Halten aus (die e2e-Tests nutzen das). Die Livewerte (`live`) gehen nur an den Dauerbetrieb: Abschaltabstand, Zuschaltabstand und
Aktivierung. Annahme (ungeprüft): Ein Wert, der nur fallen darf, kann zu niedrig bleiben, wenn ein Raum von außen wärmer wird, solange die Anlage
läuft; im Dauerbetrieb schützt davor nur der Abschaltabstand und das Ende nach `settle_s`.

Messung vom 27.10.2026 (Anlass der Änderung): Mit dem Einfrieren der ganzen Anlage blieb der SOC seit dem Anlauf bei 20 %, weil im Dauerbetrieb nie
alle Geräte ruhen, und immer dieselben vier Geräte wurden bedient, weil ihre alten Werte die Rangfolge bestimmten. Nach dem Stopp fiel die Anzeige
um 3 bis 4 K zurück, ein Offset für arbeitende Geräte bleibt offen.

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
2. **Abgabe nach dem Ersatz:** Der Ersatz ist aktiv, wenn seine Anzeige um 1 K stieg. Ob die Anlage bei der Abgabe weiterläuft, hängt am
   Nachfolger, der nach den Messungen mindestens zehn Minuten lief.
3. **Zuschalten nach Temperatur:** Zuschaltabstand 2,5 und Aktivierungsanstieg 1 sind Vorgaben des Nutzers, die an einem Lauf mit zwei Geräten (Keller, Marcel)
   erprobt sind.
4. **Wiederanlauf nach dem Selbstabschalten:** Hysterese nicht gemessen. Die Sperrzeit von etwa 4 Minuten ist nur beobachtet, die Regelung nutzt sie nicht.
5. **Überlastgrenze bedienter Räume:** Für bediente Räume gilt der Abschaltabstand statt der Überlastgrenze (Standard 3). Der Nutzer will noch prüfen, ob
   die Überhitzungs- und Überlastgrenze nur im neutralen Modus berücksichtigt werden sollen (offener Punkt der Fachspec).
6. **Kühlbetrieb:** alles gespiegelt angenommen, nicht gemessen.
7. **Messwert der Leistung fehlt:** Ohne Messwert der Außenleistung startet nur der erste Raum und die Räume werden über den Abschaltabstand und
   die Temperatur zugeschaltet. Die Messung ist Pflicht (FR-GEN-01), der Fall tritt nur beim Ausfall des Sensors auf.
