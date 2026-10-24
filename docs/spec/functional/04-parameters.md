# 4 Parameter

Startwerte, im Betrieb anzupassen. Alle Werte sind je Anlage konfigurierbar. Temperaturdifferenzen und Schrittweiten (in der Tabelle mit „K“ angegeben) gelten in der Temperatureinheit der Anlage: Bei Fahrenheit bedeutet 1 K hier 1 °F (FR-UNIT-01).

| Parameter | Startwert | Bedeutung |
| --- | --- | --- |
| Pmin | 1,3 kW | Mindestleistung im Dauerbetrieb |
| Pmax | 3,3 kW | Höchstleistung |
| Startschwelle | 80 % von Pmin | Plan darunter wird ignoriert |
| Abschaltschwelle | 50 % von Pmin | laufende Anlage bleibt bis darunter in Betrieb |
| Mindestlaufzeit Anlage | 10 min | ab jedem Start, danach gilt die Abschaltschwelle; keine Mindestpause |
| Gleichstand-Band | 1 K | Abweichungen darin gelten als gleich (zwei Gerätestufen) |
| Schrittweite Sollwert | 0,5 K | Schritt, in dem der Lastregler den Sollwert eines Innengeräts verstellt; je Innengerät einstellbar (optional), vorbelegt mit 0,5 der Temperatureinheit |
| Mindeststufe Lastregler | 2 Leistungsschritte | Untergrenze beim Nachregeln nach unten, vorzugsweise auf zwei Geräte verteilt |
| Startwert Last je Schritt | (Pmax − Pmin) / (2 × Zahl der Innengeräte) | je Innengerät, gilt bis zur ersten Messung |
| Totband Lastregler | 10 % von Pmin | Abweichung zwischen geplanter und gemessener Leistung, innerhalb der nichts nachgestellt wird |
| Wartezeit bei Planerausfall | 10 min | Geräte bleiben unverändert, bevor der Rückfall beginnt |
| Schritt des Rückfalls | 2 min | je Schritt wird eine weitere Gerätegruppe auf Heizen gestellt |
| SOC-Glättung | 15 min | Mittelwert oder Median |
| Ausreißergrenze | 2 K je Zyklus | Plausibilitätsprüfung |
| Überhitzung | 3 K, mindestens 1 h | Kühlregel |
| Regelbereich | 2 K nach unten, 2 K nach oben | je Innengerät optional; Abstand zum Sollwert, in dem der Planer den Puffer frei nutzt |
| Absolute Grenze | 3 K nach unten, 3 K nach oben | je Innengerät optional; unten hartes Minimum (Schutz), oben Überlastgrenze |
| SOC-Skala | Sollwert = 40 %, 6 K darunter = 0 %, 9 K darüber = 100 % | relativ zum aktuellen Sollwert des Raums; im Kühlbetrieb gespiegelt |
| Wirkungsgrad Puffer | 92 % | Planer-Modell |
| Entladegrenze Puffer | 3,5 kW | Planer-Modell |
| Nachtabsenkung | 21 bis 06 Uhr | senkt nur die Untergrenzen |
| Aufschlag Spätladen | 0,001 €/kWh | fällt mit der Zeit, entscheidet nur zwischen gleich teuren Zeitfenstern |
| Strafwert zwischen Regelbereich und absoluter Grenze | 0,003 €/kWh | etwas unter dem der Zoe-Ladung |
| Startwert Kapazität | 3 kWh je K (elektrisch) | gilt, bis genug Messungen vorliegen |
| Lernschritt | 0,1 K | Bezugsgröße der gelernten Energie |
| Mindestfenster Lernen | 0,35 K | kleinste Temperaturänderung je Schätzung |
| Speicher Aufzeichnung | etwa 2 MB | danach ersetzt der neue Teil den ältesten |
