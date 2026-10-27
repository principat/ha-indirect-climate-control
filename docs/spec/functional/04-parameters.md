# 4 Parameter

Startwerte, im Betrieb anzupassen. Alle Werte sind je Anlage konfigurierbar. Temperaturdifferenzen und Schrittweiten (in der Tabelle mit „K“ angegeben) gelten in der Temperatureinheit der Anlage: Bei Fahrenheit bedeutet 1 K hier 1 °F (FR-UNIT-01).

| Parameter | Startwert | Bedeutung |
| --- | --- | --- |
| Pmin | 1,3 kW | Mindestleistung im Dauerbetrieb |
| Pmax | 3,3 kW | Höchstleistung |
| Startschwelle | 80 % von Pmin | Plan darunter wird ignoriert |
| Abschaltschwelle | 50 % von Pmin | laufende Anlage bleibt bis darunter in Betrieb |
| Mindestlaufzeit Anlage | 10 min | ab jedem Start, danach gilt die Abschaltschwelle; keine Mindestpause |
| Gleichstand-Band | 1 K | Abweichungen darin gelten als gleich; gilt für die Rangfolge im Rückfall (im Betrieb zählt nur genau gleiche Abweichung) |
| Schrittweite Gerät | 0,5 K | kleinste Änderung der Gerätetemperatur, die ein Innengerät meldet; Zuschaltabstand und Aktivierungsanstieg sollen nicht kleiner sein; je Innengerät einstellbar (optional), vorbelegt mit 0,5 der Temperatureinheit |
| Mindeststufe Lastregler | 1 bedientes Gerät | Pmin; Untergrenze beim Nachregeln nach unten |
| Startwert Last je weiterem Gerät | (Pmax − Pmin) / 2 | je Innengerät, gilt bis zur ersten Messung |
| Totband Lastregler | 10 % von Pmin | Abweichung zwischen geplanter und gemessener Leistung, innerhalb der nichts nachgestellt wird |
| Abschaltabstand | 3,5 K | Gerätetemperatur über dem Sollwert, bei der sich das Gerät abregelt; Startwert aus Messungen an zwei Geräten, im Anlernmodus je Gerät zu messen (FR-LOAD-05, FR-LRN-01) |
| Zuschaltabstand | Abschaltabstand − 1 K (2,5 K) | Gerätetemperatur über dem Sollwert, ab der ein weiteres Gerät bedient wird, bevor das erste sich abregelt; der Abzug von 1 berücksichtigt die Auflösung von 0,5 K und den Versatz von bis zu 5 Minuten zwischen den Messungen (FR-LOAD-06) |
| Aktivierungsanstieg | 1 K | Anstieg der gemeldeten Gerätetemperatur (Livewert, nicht gehalten) gegenüber dem Wert beim Start, ab dem ein zugeschaltetes Gerät als aktiv gilt (FR-LOAD-06) |
| Anlaufdauer | 10 min | in dieser Zeit wird die Leistung nicht zum Herunterregeln herangezogen (FR-LOAD-07) |
| Einschwingfenster | 10 min | Länge des gleitenden Mittelwerts der gemeldeten Gerätetemperatur nach dem Stopp des letzten arbeitenden Geräts; bis das Gerät eingeschwungen ist, wird nur das Absinken übernommen (FR-SRC-02); als eingeschwungen gilt ein Gerät, wenn der Mittelwert höchstens die halbe Schrittweite Gerät vom gemeldeten Wert abweicht; 0 schaltet das Halten aus |
| Sperrzeit Außengerät | 4 min | nach einem Stopp läuft das Außengerät nicht wieder an; nur gemessen, im Anlernmodus zu lernen (FR-LRN-01) |
| Höchstzeit Aktivierung | 10 min | so lange wartet ein zugeschaltetes Gerät auf den Aktivierungsanstieg, danach gilt es als aktiv (FR-LOAD-06); zugleich längste Wartezeit der Beruhigung beim Lernen der Leistung (FR-LOAD-02) |
| Wartezeit bei Planerausfall | 10 min | Geräte bleiben unverändert, bevor der Rückfall beginnt |
| Schritt des Rückfalls | 2 min | je Schritt wird eine weitere Gerätegruppe auf Heizen gestellt |
| SOC-Glättung | 15 min | Mittelwert oder Median |
| Ausreißergrenze | 2 K je Zyklus | Plausibilitätsprüfung |
| Überhitzung | 3 K, mindestens 1 h | Kühlregel |
| Regelbereich | 2 K nach unten, 2 K nach oben | je Innengerät optional; Abstand zum Sollwert, in dem der Planer den Puffer frei nutzt |
| Absolute Grenze | 3 K nach unten, 3 K nach oben | je Innengerät optional; unten hartes Minimum (Schutz), oben Überlastgrenze |
| SOC-Skala | je Raum: unterer Randbereich 0 bis 10 %, Wohlfühlbereich 10 bis 90 % (Sollwert = 50 %), oberer Randbereich 90 bis 100 % | feste Anteile, die Grenzen sind Regelbereich und absolute Grenze des Raums, relativ zum aktuellen Sollwert; im Kühlbetrieb gespiegelt (FR-SOC-01) |
| Breite der Gewichtskurve | 0,3 | Breite der Glocke im Wohlfühlbereich, gemessen am Füllstand von 0 bis 1 (Sollwert bei 0,5); kleiner: der SOC folgt stärker dem kältesten Raum, größer: stärker dem Mittelwert; muss größer als 0 sein |
| Anzeigeversatz | 3,5 K | Abstand, um den die gemeldete Gerätetemperatur über dem gemerkten Wert liegen muss, bevor dieser nachgezogen wird, und um den er dann unter ihr liegt; wird im Betrieb angepasst (FR-SOC-03, FR-SOC-04); Startwert aus drei Läufen am 25. und 27.10.2026 |
| Obergrenze Anzeigeversatz | 1,25 mal die größte gemessene Abweichung | größte im Betrieb gemessene Abweichung der gemeldeten Gerätetemperatur über dem Sollwert ihres Raums (beim Kühlen darunter), über alle Räume; der angepasste Anzeigeversatz überschreitet sie nicht (FR-SOC-04) |
| Schwelle Anpassung Anzeigeversatz | 10 Prozentpunkte | Abweichung des SOC am Arbeitsende vom SOC nach dem Einschwingen, ab der der Anzeigeversatz angepasst wird (FR-SOC-04) |
| Zielabweichung Anpassung | 5 Prozentpunkte | Abweichung, die nach der Anpassung höchstens bleiben darf; direkte Berechnung oder Näherung (FR-SOC-04) |
| Wirkungsgrad Puffer | 92 % | Planer-Modell |
| Entladegrenze Puffer | 3,5 kW | Planer-Modell |
| Nachtabsenkung | 21 bis 06 Uhr | senkt nur die Untergrenzen |
| Aufschlag Spätladen | 0,001 €/kWh | fällt mit der Zeit, entscheidet nur zwischen gleich teuren Zeitfenstern |
| Strafwert zwischen Regelbereich und absoluter Grenze | 0,003 €/kWh | etwas unter dem der Zoe-Ladung |
| Startwert Kapazität | 3 kWh je K (elektrisch) | gilt, bis genug Messungen vorliegen |
| Lernschritt | 0,1 K | Bezugsgröße der gelernten Energie |
| Mindestfenster Lernen | 0,35 K | kleinste Temperaturänderung je Schätzung |
| Speicher Aufzeichnung | etwa 2 MB | danach ersetzt der neue Teil den ältesten |
| Leistungsschritt Aufzeichnung | 20 W | die Leistung des Außengeräts wird aufgezeichnet, wenn sie sich seit dem letzten Eintrag so stark geändert hat |
