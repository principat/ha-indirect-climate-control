# 2 Begriffe

| Begriff | Bedeutung |
| --- | --- |
| Planer | Programm, das aus Preisen, Erzeugung und Puffer einen Leistungsplan berechnet (Referenz: HAEO) |
| Plan | geplante elektrische Leistung der Klimaanlage über die Zeit |
| Klima-Puffer | virtueller Speicher im Planer, dessen Füllstand der SOC ist |
| SOC | Füllstand des Puffers in Prozent, abgeleitet aus der Gerätetemperatur des schlechtesten Raums |
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
| Übergabe | Ablösung eines bedienten Geräts an seiner Grenze durch das nächste: erst das nächste an, dann das erste in den neutralen Modus |
| Rückfall | Normalbetrieb ohne Planer nach einer Wartezeit: alle Geräte heizen schrittweise mit Standard-Sollwerten |
| Temperatureinheit | Celsius (Standard) oder Fahrenheit, je Anlage; gilt für alle Temperaturen der Klimaanlagen und für Differenzen und Schrittweiten (dort als Zahl, 1 K wird 1 °C bzw. 1 °F) |
| Betriebsart | Heizen (Standard) oder Kühlen, je Anlage, wählbar über einen optionalen externen Schalter |
| Gelernte Kapazität | elektrische Energie je 0,1 K Änderung der mittleren Gerätetemperatur, aus dem Betrieb gemessen, getrennt für Heizen und Kühlen |
| Regelbereich | Abstand zum Sollwert (je Richtung), in dem der Planer den Puffer ohne Kosten nutzen darf |
| Absolute Grenze | Abstand zum Sollwert (je Richtung), an dem Schluss ist: unten Schutz durch Heizen, oben keine weitere Beheizung (Überlastgrenze) |
| Anlaufschwelle | Sollwert, ab dem ein Innengerät Leistung vom Außengerät fordert: der Anlaufabstand unter der Gerätetemperatur |
| Leistungsschritt | eine Verstellung des Sollwerts eines Innengeräts um seine Schrittweite über der Anlaufschwelle, Stellgröße der Lastregelung |
| Mindeststufe | kleinste Last der Lastregelung: zwei Leistungsschritte auf zwei Geräten, die Leistung ist Pmin |
