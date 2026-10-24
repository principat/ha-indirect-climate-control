# 6 Offene Punkte

- [ ] Verhalten der Gerätetemperatur beim Wechsel von Heizen auf Lüften (gesättigter Lüftungslauf fehlt).
- [ ] Bezug der SOC-Skala 15 bis 30 °C auf den eigenen Sollwert je Raum.
- [ ] Gerätetemperatur in ganzen Grad (FR-SRC-01): Die Geräte melden in 0,5-K-Schritten, das Runden verwirft Information. Beschluss offen, ob die Regelung die gemeldeten Werte direkt verwendet (das Lernen tut es bereits).
- [ ] Mindestlaufzeit je Gerät, Totband und Schrittweite des Lastreglers, dynamische Lastgrenze aus dem Plan.
- [ ] Kühlbetrieb im Sommer in der Praxis prüfen: Entfeuchtung, Wärmeeintrag durch Sonne, Verhalten der Schutzregeln. Die Überlastgrenze wird am Sollwert gespiegelt und kann bei niedrigem Sollwert außerhalb der SOC-Skala liegen (dann gilt 100 %).
- [ ] Lernen der Kapazität prüfen: Genauigkeit des 0,35-K-Fensters, Einfluss des Wärmeverlusts (derzeit nicht korrigiert, Wert eher zu groß). Bisher nur an einer Simulation geprüft.
- [ ] Aufgezeichnete Betriebsdaten (FR-OBS-01) auswerten.
