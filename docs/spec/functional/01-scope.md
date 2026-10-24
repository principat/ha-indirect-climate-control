# 1 Zweck und Abgrenzung

Ein Planer plant die Klimaanlage als thermischen Puffer. Bei Überschuss aus Erzeugung am Tag und bei
günstigen Preisen nachts wird direkt geheizt, statt den Umweg über einen Batteriespeicher zu gehen.
Die Steuerung folgt dem Plan über Betriebsmodi und Sollwert-Offsets der Innengeräte. Die Leistung des
Außengeräts wird nicht direkt gesetzt, sie ergibt sich aus Modus, Zahl der laufenden Innengeräte und
Abstand zwischen Soll- und Gerätetemperatur.

Die Lösung ist allgemein gehalten: Zahl der Geräte, Leistungsklassen, Pmin und Pmax sind konfigurierbar.
Der Referenzfall (Abschnitt 5) dient als Entwicklungstemplate.

**Teil des Projekts:** SOC bilden, Plan lesen, Geräte und Offsets wählen, Moduswechsel, Lastregelung,
Sicherheit, Rückfall, Vorgaben für das Planer-Modell, Betriebsart Heizen oder Kühlen, Lernen der
Pufferkapazität aus dem Betrieb, Aufzeichnung der Betriebsdaten.

**Nicht Teil des Projekts:** die Optimierung selbst, die Prognose der Heizlast aus der Wetterprognose
(beides Sache des Planers) und Änderungen am Planer-Kern.

**Bewusst nicht vorgesehen:** eine Mindestlaufzeit je Innengerät (entschieden am 24.10.2026) und eine eigene dynamische Lastgrenze aus dem Plan (der Plan enthält nur die Soll-Last, die Obergrenze Pmax hält der Planer selbst ein).
