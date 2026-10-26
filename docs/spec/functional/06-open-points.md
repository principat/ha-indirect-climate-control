# 6 Offene Punkte

- [x] Verhalten der Gerätetemperatur beim Wechsel von Heizen auf Lüften: gemessen am 26.10.2026, siehe docs/environment/devices-lg-multi-v.md (Abfall um 2,5 bis 3,5 K in 10 Minuten, danach etwa 0,5 K je 10 bis 15 Minuten).
- [ ] Überhitzungsgrenze (FR-SAFE-03) und Überlastgrenze nur im neutralen Modus (Lüften) berücksichtigen? Die Anzeige ist dort nach der Einschwingzeit verlässlich, bei arbeitenden Geräten nicht.
- [ ] Abgabe eines Geräts (FR-LOAD-08): Läuft die Anlage weiter, wenn das erste Gerät erst nach aktivem Nachfolger und steigender Leistung abgegeben wird? Messung mit Wohnen und Schlafen läuft.
- [ ] Wann laufen Geräte nach dem Selbstabschalten bei Sollwert plus 3,5 wieder an (Hysterese)? Nicht gemessen. Der Abschaltabstand liegt nach zwei Geräten zwischen 3,5 und 4 K.
- [ ] Hängt die Leistung je Gerät von der Außentemperatur ab? Beim Anlernen bewusst nicht berücksichtigt (FR-LRN-01).
- [ ] Kühlbetrieb im Sommer in der Praxis prüfen: Entfeuchtung, Wärmeeintrag durch Sonne, Verhalten der Schutzregeln. Überhitzungsregel (3 K, 1 h) und absolute Grenze nach oben (3) überlappen sich: prüfen, ob beide nötig sind.
- [ ] Lernen der Kapazität prüfen: Genauigkeit des 0,35-K-Fensters, Einfluss des Wärmeverlusts (derzeit nicht korrigiert, Wert eher zu groß). Bisher nur an einer Simulation geprüft.
- [ ] Aufgezeichnete Betriebsdaten (FR-OBS-01) auswerten.
- [ ] Lastregelung (FR-LOAD-01/02): Beruhigungskriterium (Totband über drei Regelzyklen, Höchstzeit) und Lernrate an Messwerten prüfen, Reaktionszeit der Außenleistung messen.
