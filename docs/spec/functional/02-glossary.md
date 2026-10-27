# 2 Begriffe

| Begriff | Bedeutung |
| --- | --- |
| Planer | Programm, das aus Preisen, Erzeugung und Puffer einen Leistungsplan berechnet (Referenz: HAEO) |
| Plan | geplante elektrische Leistung der Klimaanlage über die Zeit |
| Klima-Puffer | virtueller Speicher im Planer, dessen Füllstand der SOC ist |
| SOC | Füllstand des Puffers in Prozent, abgeleitet aus den Gerätetemperaturen aller Räume: 10 % Durchschnitt der unteren Randbereiche, 80 % gewichtetes Mittel der Wohlfühlbereiche (kalte Räume zählen stärker), 10 % Durchschnitt der oberen Randbereiche (FR-SOC-01) |
| Wohlfühlbereich | mittlere 80 % der SOC-Skala eines Raums: der Regelbereich, mit dem Sollwert bei 50 % |
| Randbereich | untere und obere 10 % der SOC-Skala eines Raums: unten von der absoluten Grenze bis zur Untergrenze des Regelbereichs, oben von dessen Obergrenze bis zur absoluten Grenze |
| Füllstand (eines Abschnitts) | Lage der Gerätetemperatur eines Raums in einem Abschnitt seiner SOC-Skala, von 0 (unteres Ende) bis 1 (oberes Ende), außerhalb begrenzt |
| Gewichtskurve | linke Hälfte einer Gaußschen Glockenkurve über dem Wohlfühlbereich: Gewicht 1 am kalten Ende, stark abfallend zum warmen Ende; ihre Breite ist ein Parameter |
| Innengerät | Gerät im Raum mit eigenem Sollwert, Modus und Gerätetemperatur |
| Außengerät | gemeinsames Gerät, dessen Leistung gesteuert wird |
| Gerätetemperatur | Ist-Temperatur, die das Innengerät meldet (einzige Temperaturquelle) |
| Abweichung | Sollwert minus Gerätetemperatur eines Raums |
| Neutraler Modus | Lüften (Standard) oder Aus; trennt Heizen und Kühlen |
| Kühlklasse | Kühlen und Entfeuchten |
| Pmin / Pmax | kleinste Dauerleistung / größte Leistung des Außengeräts |
| Startschwelle / Abschaltschwelle | Anteile von Pmin, ab denen gestartet bzw. unter denen abgeschaltet wird |
| Leistungsklasse | Gruppe von Innengeräten gleicher Nennleistung |
| Gleichstand-Band | Spanne, in der Abweichungen als gleich gelten |
| Rückfall | Normalbetrieb ohne Planer nach einer Wartezeit: alle Geräte heizen schrittweise mit Standard-Sollwerten |
| Temperatureinheit | Celsius (Standard) oder Fahrenheit, je Anlage; gilt für alle Temperaturen der Klimaanlagen und für Differenzen und Schrittweiten (dort als Zahl, 1 K wird 1 °C bzw. 1 °F) |
| Betriebsart | Heizen (Standard) oder Kühlen, je Anlage, wählbar über einen optionalen externen Schalter |
| Gelernte Kapazität | elektrische Energie je 0,1 K Änderung der mittleren Gerätetemperatur, aus dem Betrieb gemessen, getrennt für Heizen und Kühlen |
| Regelbereich | Abstand zum Sollwert (je Richtung), in dem der Planer den Puffer ohne Kosten nutzen darf |
| Absolute Grenze | Abstand zum Sollwert (je Richtung), an dem Schluss ist: unten Schutz durch Heizen, oben keine weitere Beheizung (Überlastgrenze) |
| Mindeststufe | kleinste Last der Lastregelung: ein bedientes Innengerät, die Leistung ist Pmin |
| Abschaltabstand | Abstand der Gerätetemperatur über dem Sollwert, bei dem sich das Innengerät selbst abregelt und das bediente Gerät abgegeben wird (Startwert 3,5) |
| Zuschaltabstand | Abstand der Gerätetemperatur über dem Sollwert, ab dem ein weiteres Gerät bedient wird, wenn die Leistung nicht unterschritten ist: 1 unter dem Abschaltabstand (Startwert 2,5) |
| Aktiv | Ein zugeschaltetes Gerät gilt als aktiv, wenn seine gemeldete Gerätetemperatur (Livewert, nicht der gehaltene Wert) seit seinem Start um den Aktivierungsanstieg gestiegen ist |
| Anlaufphase | Zeit nach dem Start der Anlage oder dem Zuschalten eines Geräts, in der die Leistung nicht zum Herunterregeln herangezogen wird (Startwert 10 Minuten) |
| Pufferraum | Raum, dessen Gerätetemperatur seinen Sollwert erreicht oder überschritten hat; sein Gerät erhält als Gerätesollwert den Sollwert plus den Regelbereich (Heizen) beziehungsweise minus den Regelbereich (Kühlen) |
| Halten | Ein arbeitendes Gerät behält für die Bewertung seines Raums den zuletzt bewerteten Wert der Gerätetemperatur, jedes andere Gerät kann seinen Wert nur nach unten korrigieren, solange irgendein Gerät arbeitet und für die Einschwingzeit danach |
| Einschwingzeit | Zeit, die die Gerätetemperatur nach dem Wechsel in den neutralen Modus braucht, bis sie den Raum wieder abbildet (Startwert 10 Minuten) |
| Sperrzeit | Zeit nach einem Stopp des Außengeräts, in der es nicht wieder anläuft (beobachtet etwa 4 Minuten) |
| Anlernmodus | vom Nutzer gestarteter Ablauf, der die Eigenschaften der Innengeräte und des Außengeräts misst (FR-LRN-01) |
