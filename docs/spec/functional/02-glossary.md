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
| Rückfall | Normalbetrieb ohne Planer nach einer Wartezeit: alle Geräte heizen schrittweise mit Standard-Sollwerten |
