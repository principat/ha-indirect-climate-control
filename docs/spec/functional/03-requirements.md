# 3 Anforderungen

| ID | Anforderung | Status | Ebenen |
| --- | --- | --- | --- |
| FR-PLAN-01 | Die Steuerung liest die geplante Leistung für jetzt und die folgenden Stunden. | beschlossen | unit,integration,e2e |
| FR-PLAN-02 | Start erst ab Startschwelle (80 % von Pmin). Eine laufende Anlage bleibt in Betrieb, bis der Plan unter die Abschaltschwelle (50 % von Pmin) fällt, mindestens aber 10 Minuten ab ihrem Start (Mindestlaufzeit, gezählt ab jedem Start, nicht ab Laständerungen; in dieser Zeit wird mindestens Pmin angefordert). Darunter wird der Plan ignoriert, alle Geräte gehen in den neutralen Modus. Nach einer Pause darf sofort wieder gestartet werden. Es gibt keinen Pulsbetrieb. | beschlossen | unit |
| FR-PLAN-03 | Im Betrieb wird mindestens Pmin angefordert. Ein Überschuss gegenüber dem Plan geht in den SOC, der Planer plant danach entsprechend weniger. | beschlossen | unit |
| FR-PLAN-04 | Der Plan hat Vorrang vor der Regelung. Läufe werden nur verlängert, wenn der Planer Laden vorsieht. | beschlossen | unit |
| FR-SRC-01 | Als Temperatur zählt allein die Gerätetemperatur des Innengeräts (ganze Grad). Raumsensoren werden nicht verwendet. | beschlossen | unit,integration |
| FR-SOC-01 | Der SOC kommt vom schlechtesten Raum, jeder Raum gegen seinen eigenen Sollwert. Überhitzte Räume verfälschen ihn nicht. | beschlossen | unit |
| FR-SOC-02 | Der SOC wird über etwa 15 Minuten geglättet. Sprünge über 2 K in einem Zyklus gelten als Ausreißer. | beschlossen | unit |
| FR-DIST-01 | Geräte werden nach Abweichung priorisiert: größere Abweichung, höhere Priorität. | beschlossen | unit |
| FR-DIST-02 | Bei Gleichstand (innerhalb des Bandes) wird nach Leistungsklasse gruppiert, in der angelegten Reihenfolge. Die Gruppen dienen der Lastbalancierung. Dadurch werden alle Räume erst auf ein gemeinsames Niveau gezogen und steigen dann parallel. | beschlossen | unit |
| FR-DIST-03 | Mindestlaufzeit je Gerät, damit die Rangfolge nicht ständig wechselt. | offen | unit |
| FR-MODE-01 | Heizen und Kühlen wechseln nur über den neutralen Modus. Entfeuchten zählt zur Kühlklasse. Vom neutralen Modus zu Aus oder Heizen darf gewechselt werden, solange kein anderes Gerät kühlt. | beschlossen | unit,integration |
| FR-MODE-02 | Nach jedem Wechsel auf Heizen oder Kühlen wird der Sollwert erneut gesetzt. | beschlossen | integration,e2e |
| FR-MODE-03 | Neutraler Modus im Normalzustand ist Lüften, nicht Aus. | beschlossen | unit |
| FR-SEAS-01 | Die Anlage hat die Betriebsart Heizen oder Kühlen. Heizen ist der Standard. Optional kann ein externer Schalter mit zwei Zuständen angegeben werden: aus bedeutet Heizen, ein bedeutet Kühlen. Ohne Schalter oder bei nicht verfügbarem Schalter gilt Heizen. Heizen und Kühlen laufen nie gleichzeitig, der Wechsel läuft über den neutralen Modus (FR-MODE-01). | beschlossen | unit,integration,e2e |
| FR-SEAS-02 | Im Kühlbetrieb gilt dieselbe Regelung gespiegelt: Der Puffer ist ein Kältespeicher, der SOC steigt mit sinkender Gerätetemperatur (30 °C = 0 %, 15 °C = 100 %), die Abweichung ist Gerätetemperatur minus Sollwert, die Geräte werden auf Kühlen gestellt, Obergrenze (Überlast) und Untergrenzen werden gespiegelt an den Planer gemeldet. Der Schutz der Räume wird gespiegelt: Über dem harten Maximum (Sollwert plus 2 K) wird auch ohne Plan gekühlt, liegt ein Raum mindestens 3 K unter dem Sollwert seit mindestens 1 h, wird geheizt, nur im neutralen Zustand. Der Rückfall stellt die Geräte schrittweise auf Kühlen mit Standard-Sollwerten. | beschlossen | unit,integration |
| FR-LOAD-01 | Ein Lastregler vergleicht geplante und gemessene Außenleistung (5-Minuten-Mittel) und stellt Offsets (Schritt 0,5 K, Wartezeit 2 Minuten) oder Gerätezahl in beide Richtungen nach. | Vorschlag | unit,integration |
| FR-SAFE-01 | Ein Raum mit offenem Fenster wird aus der Regelung genommen. | beschlossen | unit,integration |
| FR-SAFE-02 | Fällt ein Raum unter das harte Minimum (Sollwert minus 2 K), wird er geheizt, auch ohne Plan. Der Schutz hat Vorrang vor dem Plan. | beschlossen | unit,integration |
| FR-SAFE-03 | Liegt ein Raum mindestens 3 K über dem Sollwert, seit mindestens 1 h, wird gekühlt. Das gilt für alle Räume. Heizen hat Vorrang, gekühlt wird nur im neutralen Zustand (kein Gerät heizt). | beschlossen | unit,integration |
| FR-SAFE-04 | Ist der Plan veraltet oder der Planer ausgefallen, bleiben die Geräte zunächst unverändert (Wartezeit 10 Minuten, das Gebäude ist träge), der Schutz der Räume gilt weiter. Kommt der Plan in dieser Zeit zurück, ändert sich nichts. Dauert der Ausfall länger, gilt der Rückfall: Die Geräte werden schrittweise auf Heizen mit Standard-Sollwerten gestellt, größte Abweichung zuerst, je Schritt eine Gruppe, bereits laufende Geräte bleiben an. Nur dieser Ausfall wird automatisch abgefangen, alle anderen Störungen behebt der Betreiber manuell. | beschlossen | unit,integration,e2e |
| FR-PLNR-01 | Die Integration liefert dem Planer die Vorgaben für den Puffer: Entladegrenze, Wirkungsgrad, gewichtete Untergrenzen, Nachtabsenkung (senkt nur die Untergrenzen), Strafzone zwischen Sollwert und hartem Minimum, Überlast mit Aufschlag, Aufschlag für spätes Laden. Werte siehe Parameter. | beschlossen | unit,integration |
| FR-PLNR-02 | Die Pufferkapazität wird im Betrieb gelernt: Gemessen wird die elektrische Energie des Außengeräts je 0,1 K Änderung der flächengewichteten mittleren Gerätetemperatur, im Heizbetrieb und im Kühlbetrieb getrennt, jeweils nur während die Anlage läuft. Jede Schätzung beruht auf einer Änderung von mindestens 0,35 K (Auflösung der Geräte). Die Wände bleiben unberücksichtigt. Das Lernen nutzt allein die gemessene Leistung des Außengeräts und die Gerätetemperaturen, keine Prognose und keine Angaben aus anderen Programmen. Ausgangswert ist 3 kWh je Kelvin (elektrisch), der gelernte Wert bleibt über Neustarts erhalten. Messfenster werden bei Stopp, Rückfall, offenem Fenster oder geänderter Raumzahl verworfen. | beschlossen | unit,integration |
| FR-PLNR-03 | Die gelernten Werte (Heizen, Kühlen, Zahl der Schätzungen, letzte Aktualisierung) sind in der Diagnose sichtbar, aber nicht änderbar. Zurückgesetzt werden sie nur über eine eigene Funktion, die im Alltag nicht angeboten wird und für grundlegende Änderungen an der Anlage gedacht ist. | beschlossen | unit,integration |
| FR-GEN-01 | Zahl und Namen der Räume, Leistungsklassen, Pmin, Pmax und alle Parameter sind konfigurierbar. Die Messung der elektrischen Leistung des Außengeräts ist eine Pflichtangabe der Anlage. Keine Anlagenwerte im Kern. | beschlossen | unit,integration,e2e |
| FR-CFG-01 | Innengeräte werden einzeln erfasst. Jedes kann für sich hinzugefügt, geändert und entfernt werden, ohne die übrige Einrichtung zu wiederholen. | beschlossen | integration,e2e |
| FR-CFG-02 | Mehrere voneinander unabhängige Anlagen können gleichzeitig betrieben werden. | beschlossen | integration |
| FR-CFG-03 | Über jedem Einstellungsfeld mit nicht trivialem Inhalt steht ein einklappbarer Erklärtext, mit dem der Nutzer die Einstellung ohne weitere Unterlagen pflegen kann. Ein Schalter legt fest, ob die Erklärtexte beim Öffnen der Einstellungen auf- oder zugeklappt sind. | beschlossen | unit,integration |
| FR-OBS-02 | Für jedes Innengerät werden zur Diagnose angezeigt: Abweichung zum Sollwert, Wärmebedarf bis zum Sollwert und verbleibende Speicherkapazität bis zur Überlastgrenze. | beschlossen | unit,integration |
| FR-OBS-01 | Betriebsdaten (Start, Stopp, Gerätetemperatur, Sollwert, Modus, Lüfterstufe) werden fortlaufend aufgezeichnet. | Vorschlag | integration |
| NF-CFG-01 | Die Konfiguration wird gegen eine echte Instanz der Zielplattform geprüft, nicht nur gegen Mocks. | beschlossen | e2e |
| NF-TEST-01 | Jede Anforderung mit Status beschlossen ist auf allen genannten Ebenen getestet. | beschlossen | unit |
| NF-REL-01 | Veröffentlichung, Versionsnummer und Änderungsprotokoll entstehen automatisch aus den Commit-Nachrichten. | beschlossen | unit |
| NF-SPEC-01 | Die fachliche Spezifikation enthält keine Technologiebegriffe. | beschlossen | unit |

## Abnahmeszenarien (Auszug)

**FR-PLAN-02 Schwelle.** Gegeben Pmin 1,3 kW und Anlage aus. Wenn der Plan 1,0 kW zeigt, bleibt sie aus (unter 1,04 kW).
Wenn er 1,1 kW zeigt, startet sie mit mindestens 1,3 kW. Läuft sie, bleibt sie bei 0,8 kW Plan an und geht bei 0,6 kW aus (unter 0,65 kW), frühestens jedoch 10 Minuten nach ihrem Start. Fällt der Plan davor auf 0 und steigt wieder, läuft sie ununterbrochen weiter.

**FR-DIST-02 Gleichstand.** Gegeben Räume A (Abweichung 3 K), B und C (je 1 K) und Band 1 K. Zuerst wird A bedient.
Sinkt A auf 1 K, sind alle gleichauf und werden nach Gruppe und angelegter Reihenfolge parallel bedient.

**FR-MODE-01 Moduswechsel.** Gegeben ein Gerät kühlt. Soll ein anderes heizen, gehen erst alle Geräte in den neutralen Modus,
dann in den Zielmodus, danach werden die Sollwerte neu gesetzt.

**FR-SAFE-04 Rückfall.** Gegeben der Plan ist älter als seine Gültigkeit. Dann bleiben die Geräte 10 Minuten unverändert. Kommt der Plan nicht zurück, wird alle 2 Minuten eine weitere Gruppe auf Heizen mit Standard-Sollwerten gestellt, bis alle Geräte heizen. Fällt ein Raum in dieser Zeit unter das harte Minimum, wird er sofort geheizt.

**FR-SEAS-01/02 Kühlbetrieb.** Gegeben der Schalter steht auf ein. Dann kühlen die bedienten Geräte, der SOC steigt, wenn die Gerätetemperaturen sinken, und der Planer erhält die gespiegelten Grenzen. Fällt der Schalter aus oder fehlt er, wird geheizt. Beim Umschalten gehen alle Geräte erst in den neutralen Modus, dann in den Zielmodus.

**FR-PLNR-02 Lernfenster.** Gegeben die Anlage läuft und die mittlere Gerätetemperatur steigt um 0,1 K. Dann entsteht noch keine Schätzung. Erst bei einer Änderung von mindestens 0,35 K im Fenster wird die Energie je 0,1 K berechnet und der gelernte Wert angepasst.
