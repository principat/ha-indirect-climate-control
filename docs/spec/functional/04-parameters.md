# 4 Parameter

Startwerte, im Betrieb anzupassen. Alle Werte sind je Anlage konfigurierbar.

| Parameter | Startwert | Bedeutung |
| --- | --- | --- |
| Pmin | 1,3 kW | Mindestleistung im Dauerbetrieb |
| Pmax | 3,3 kW | Höchstleistung |
| Startschwelle | 80 % von Pmin | Plan darunter wird ignoriert |
| Abschaltschwelle | 50 % von Pmin | laufende Anlage bleibt bis darunter in Betrieb |
| Mindestlaufzeit Anlage | 10 min | ab jedem Start, danach gilt die Abschaltschwelle; keine Mindestpause |
| Gleichstand-Band | 1 K | Abweichungen darin gelten als gleich (Auflösung der Geräte) |
| Offset-Schritt | 0,5 K | je Regelschritt |
| Wartezeit | 2 min | nach jedem Schritt |
| Wartezeit bei Planerausfall | 10 min | Geräte bleiben unverändert, bevor der Rückfall beginnt |
| Schritt des Rückfalls | 2 min | je Schritt wird eine weitere Gerätegruppe auf Heizen gestellt |
| Lastmittel | 5 min | Messung der Außenleistung |
| SOC-Glättung | 15 min | Mittelwert oder Median |
| Ausreißergrenze | 2 K je Zyklus | Plausibilitätsprüfung |
| Überhitzung | 3 K, mindestens 1 h | Kühlregel |
| Hartes Minimum | Sollwert minus 2 K | Schutz |
| Überlast | bis 28 °C, mit Aufschlag | Obergrenze des Puffers, je Raum festzulegen (raumabhängig) |
| SOC-Skala | 15 bis 30 °C = 0 bis 100 % | Bezug auf eigenen Sollwert offen |
| Wirkungsgrad Puffer | 92 % | Planer-Modell |
| Entladegrenze Puffer | 3,5 kW | Planer-Modell |
| Nachtabsenkung | 21 bis 06 Uhr | senkt nur die Untergrenzen |
| Aufschlag Spätladen | 0,001 €/kWh | fällt mit der Zeit, entscheidet nur zwischen gleich teuren Zeitfenstern |
| Strafwert Sollwert bis hartes Minimum | 0,003 €/kWh | etwas unter dem der Zoe-Ladung |
| Mindestlaufzeit je Gerät | offen | siehe FR-DIST-03 |
