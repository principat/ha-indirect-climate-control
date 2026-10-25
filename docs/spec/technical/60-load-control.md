# 60 Lastregelung über Temperaturereignisse

Status: **umgesetzt am 25.10.2026** (`core/load.py`, `core/rotation.py`, Anbindung in `controller.py` und `coordinator.py`). Grundlage
sind FR-LOAD-01 bis FR-LOAD-04 und die Vorgaben des Nutzers aus diesem Gespräch. Das Konzept ist an Messwerten noch nicht geprüft.

## Warum keine festen Zeitfenster

Erreicht ein Innengerät seinen Zielwert, zieht es keine Leistung mehr. Die Last am Außengerät fällt, wird aber verzögert gemessen. Ein
Regler mit festem Fenster merkt es erst, wenn das Außengerät schon ausgeht und unnötig taktet. Das Ereignis, auf das es ankommt, ist
die Änderung der Gerätetemperatur (0,5-K-Schritte). Die Anlage reagiert nicht synchron darauf, deshalb braucht der Regler ein
Gedächtnis dafür, welche Last ein Schritt bewirkt.

## Vorgaben des Nutzers

- **Ein Raum, im Wechsel (Stand 25.10.2026).** Beobachtung der Läufe vom 24. und 25.10.2026 (Version 0.8.0, zwei Geräte mit je einem Schritt,
  Plan 1,3 kW): Die Außenleistung stand drei bis fünf Minuten bei etwa 1,2 kW, stieg dann auf 2,1 bis 2,3 kW, obwohl die Schritte
  konstant blieben. Annahme des Nutzers: Zwei Geräte sind zu viel, das erste hält Pmin, das zweite legt nach einigen Minuten rund 1 kW
  dazu. Kleine Räume heizen schnell (Bad 5 K in 15 min), die Geräte melden in 0,5-K-Schritten. Daher ein Raum, bei mehr Leistung ein
  zweites Gerät, um die halbe Wechselzeit versetzt. Die Räume wechseln sich mit Überlapp ab und werden dazwischen gelüftet.
- **Nächster Raum:** die größte Abweichung, nur bei genau gleicher Abweichung entscheidet die Leistungsklasse. Für einen Raum, der
  bedient wurde und dessen Gerät noch nichts Neues gemeldet hat, gilt ein angenommener Anstieg um einen Schritt. Steigt die Anzeige des
  bedienten Raums um mehr als die Schrittweite, wird sofort gewechselt.
- **Wenn mehr als Pmin gefordert ist**, wird ein zweites Gerät mit einem Versatz von der halben Wechselzeit gestartet.
- **Totband bleibt: 10 % von Pmin** um die angeforderte Leistung (für die Zahl der Geräte).
- **Bezug ist die angeforderte Leistung** (mindestens Pmin im Betrieb, FR-PLAN-03), nicht die reine Planleistung.
- **Zurücksetzen** beim Stopp der Anlage und beim Wechsel der Betriebsart auf den Standard.
- **Die Leistung eines weiteren Geräts wird je Innengerät gelernt.** Die Lüfterstufe braucht keinen eigenen Schlüssel, sie steckt in der
  gelernten Geräteleistung. Eine Änderung der Lüfterleistung würde den Komfort beeinflussen und kommt als Stellgröße nicht in Frage.
- **Anlauf (Messung des Nutzers):** Bei einem Sollwert von 20 °C läuft ein Gerät schon bei einer Anzeige von 22 °C an (Gerät an der
  Decke).
- **Startwert je weiterem Gerät:** (Pmax − Pmin) / 2, also 1 kW bei 1,3 und 3,3 kW. Das stützt sich auf die Läufe (zweites Gerät etwa
  +1 kW) und nimmt an, dass Pmax mit drei Geräten erreicht wird. Beides ist nicht einzeln gemessen.

## Mechanismus

1. **Anlaufschwelle und Schritt.** Ein Innengerät an der Decke misst zu warm und läuft schon an, wenn seine Anzeige um den
   Anlaufabstand `start_offset` (Standard 2, je Innengerät, in der Einheit der Anlage) über dem Sollwert liegt, bei einem Sollwert von
   20 °C also bei 22 °C. Die Anlaufschwelle liegt daher beim Heizen **unter** der Gerätetemperatur: `Sollwert = Gerätetemperatur −
   Anlaufabstand + Schrittweite` für das bediente Gerät (ein Schritt), begrenzt durch die absolute Grenze des Raums. Die Schrittweite
   `step` ist je Innengerät einstellbar (Standard 0,5). Im Kühlbetrieb gilt es gespiegelt (Annahme, nicht gemessen).
2. **Zahl der Geräte.** Die erwartete Last ist `0` ohne bedientes Gerät, sonst `Pmin + p̄ × (Zahl − 1)`, mit `p̄` als Mittel der
   gelernten Leistung der bedienten Geräte (`core/load.py: expected_load_w`). `_lanes_wanted` wählt die Zahl der gleichzeitig
   bedienten Geräte aus der angeforderten Leistung: Ist der Abstand größer als das Totband und ein Gerät mehr (weniger) näher an der
   Anforderung, wird eines ergänzt (gestrichen), mindestens eines im Betrieb, höchstens `1 + round((Pmax − Pmin) / p̄)` und höchstens die
   Zahl der zulässigen Räume. Die Rechnung läuft bei jedem Zyklus und Ereignis, es gibt kein festes Fenster.
3. **Wechselbetrieb** (`core/rotation.py`). Jedes bediente Gerät belegt eine Bahn (`Lane`: Raum, Beginn, Anzeige bei Beginn). Eine
   Bahn gibt ihren Raum ab, wenn die Wechselzeit (`rotation_s`, Standard 120 s, 5 s Toleranz wegen des Zyklus) um ist, wenn die Anzeige des
   Raums seit Beginn um mehr als `step` gestiegen ist (Heizen, im Kühlen gespiegelt; genau ein Schritt reicht nicht) oder wenn der Raum
   nicht mehr zulässig ist (Überlastgrenze, Fenster, kein Wert). Der nächste Raum ist der erste der Rangfolge, der keine Bahn hat. Die
   Rangfolge (`rank` mit 1e-9 als Band) ordnet nach der Abweichung mit dem angenommenen Anstieg, bei genau gleicher Abweichung nach Gruppe
   und angelegter Reihenfolge. Ist kein anderer Raum frei, bleibt der Raum. Eine weitere Bahn startet, wenn seit dem Beginn der jüngsten
   Bahn mindestens `rotation_s / (Zahl der Bahnen + 1)` vergangen sind, also für die zweite die halbe Wechselzeit. Wird die Zahl der
   Geräte verringert, endet die Bahn des Raums mit der geringsten Abweichung ohne Ersatz.
4. **Angenommener Anstieg.** Verlässt ein Raum seine Bahn und hat sein Gerät in dieser Zeit keinen neuen Wert gemeldet (Anzeige gleich der
   bei Beginn), gilt er mit einem zusätzlichen Schritt (`step`, je weitere Bedienung ohne neuen Wert aufsummiert) als erwärmt:
   `Rotation.effective` liefert die Anzeige plus Anstieg, der Controller bildet die Rangfolge daraus. Meldet das Gerät einen anderen Wert,
   verfällt die Annahme. Die Grenzen (Zulässigkeit, Schutz) verwenden stets die gemeldete Anzeige.
5. **Gelernt wird `p_i`** nur, wenn sich die Zahl der Geräte ändert (nicht beim Wechsel eines Raums): Die Außenleistung wird beobachtet,
   bis sie sich beruhigt hat (siehe Beruhigung). Die gemessene Änderung geteilt durch die erwartete bestimmt einen Faktor, mit dem die
   Werte der beteiligten Geräte skaliert werden. Ein Lauf aus dem Stillstand erreicht nur Pmin und lehrt nichts. Beobachtungen, in die ein
   anderes Ereignis hineinspielt (Betriebsartwechsel, Fenster, Raum unter Schutz, laufende Übergabe), werden verworfen. Da der Wechselbetrieb
   fast immer eine Übergabe laufen hat, ist das Lernen damit weitgehend ausgesetzt (siehe Offen). Die Werte bleiben über Neustarts erhalten
   und sind in der Diagnose sichtbar, nicht änderbar.
6. **Startwert** `p_i = (Pmax − Pmin) / 2` je weiterem Gerät.

## Erster Blick auf die vorhandenen Daten (ungeprüft)

Läufe der Version 0.8.0 (zwei Geräte, Plan 1,3 kW), 24.10.2026 23:27 bis 23:37 und 25.10.2026 00:02 bis 00:15: Plateau bei 1,2 kW für drei bis
fünf Minuten, dann Anstieg auf 2,08 und 2,33 kW bei unveränderten Schritten (Wohnen/Jelle, Keller/Isa). Die vorherigen Läufe (0.7.0,
Sollwerte 2 K über der Anzeige) zeigten dasselbe Muster. Die Erklärung „acht Schritte über der Schwelle“ trägt damit nicht allein. Die
Erklärung des Nutzers „zwei Geräte sind zu viel“ ist die Grundlage der jetzigen Umsetzung, aus den Daten allein nicht zu trennen. Ein Lauf mit
nur einem Raum (Version 0.9.x) zeigt, ob die Außenleistung bei Pmin bleibt.

## Beruhigung der Außenleistung (allgemein, ohne Zahlen einer bestimmten Anlage)

Das Kriterium nutzt nur Größen, die die Integration für jede Anlage kennt oder selbst misst:

1. **Takt:** Die Leistung wird je Regelzyklus gemittelt (Parameter `cycle_s`, Standard 60 s). Das macht das Kriterium unabhängig davon,
   wie oft der Leistungssensor meldet.
2. **Toleranz = Totband** (10 % von Pmin). Die Leistung gilt als beruhigt, wenn die Mittelwerte der letzten drei Regelzyklen höchstens
   ein Totband auseinanderliegen. Die Toleranz wächst und schrumpft mit der Größe der Anlage, Watt-Schwellen gibt es nicht.
3. **Höchstzeit:** Wird die Leistung nicht beruhigt, wird die Beobachtung verworfen (kein Lernen, der bisherige Wert bleibt). Die
   Höchstzeit ist ein Parameter mit Standard 10 Minuten. Sie passt sich der Anlage an: Nach den ersten beruhigten Beobachtungen gilt
   das Dreifache der beobachteten mittleren Beruhigungszeit, höchstens der Parameter und mindestens drei Regelzyklen. Eine
   langsame Anlage bekommt so automatisch mehr Zeit, eine schnelle lernt häufiger.
4. **Dauerhaft schwankende Leistung** (Takten, Abtauen) beruhigt sich nicht, das Lernen pausiert dann von selbst. Das ist gewollt: Es
   gibt dann keine saubere Zuordnung der Änderung zum Schritt.

Das Kriterium ist eine Annahme, bis es an Messwerten geprüft ist. Die Beobachtungen werden in der Aufzeichnung (FR-OBS-01) um Beruhigungszeit
und Änderung ergänzt, damit man es an echten Daten prüfen kann.

## Übergabe (FR-LOAD-03)

`Controller._begin_handover`, `_finish_handover` und `_holds`. Gibt ein Raum seine Bahn an einen anderen ab (Wechselzeit, Anstieg über der
Schrittweite, Überlastgrenze, `LoadControl.replaced`), wird er nicht aus den Bedienten gestrichen, sondern in `_retiring` geführt: Er behält
einen Schritt (und damit den Sollwert Gerätetemperatur + Schrittweite − Anlaufabstand, begrenzt auf die Grenze des Raums), zählt aber nicht
mehr zur erwarteten Last. Die neuen Bahnen tragen die ganze angeforderte Leistung allein. In dieser Zeit laufen beide, die Last ist kurz höher
als angefordert. Die Beobachtung der Außenleistung wird verworfen (`disturbed`), solange ein Raum übergibt.

Freigegeben wird ein Raum (neutraler Modus), wenn alle bedienten Geräte im Zustand den Modus und Sollwert zeigen, den der letzte Zyklus
befohlen hat (`_holds`, Vergleich auf 0,01), wenn die Höchstzeit (`load_settle_max_s`, 10 min, wie bei der Beruhigung) abgelaufen ist oder
wenn kein Raum bedient wird (z. B. alle Räume an der Grenze). Ist kein Raum zulässig, endet der Lauf wie bisher sofort. Beim Stopp, bei
Rückfall, fehlendem Plan und Wechsel der Betriebsart wird `_retiring` geleert.

Annahme, nicht gemessen: Das Gerät „hält“ seinen Sollwert, sobald sein gemeldeter Sollwert dem befohlenen entspricht. Ob die Last des neuen
Geräts bis dahin am Außengerät angekommen ist, wird nicht geprüft (Anlauf etwa eine Minute). Bei einer Wechselzeit von 2 Minuten und einem
Zyklus von einer Minute wird ein Raum meist im Zyklus nach seinem Start freigegeben.

## Offen (Annahmen, bis zur Prüfung an Messwerten)

1. **Mindeststufe = ein Gerät = Pmin:** nach den Läufen vom 24./25.10.2026 vermutet, nicht an einem einzelnen Gerät gemessen.
2. **Startwert (Pmax − Pmin) / 2 je weiterem Gerät** und die Obergrenze von drei Geräten bei Pmax 3,3 kW: aus den Läufen abgeleitet, nicht einzeln
   gemessen.
3. **Wechselzeit 2 Minuten:** Vorgabe des Nutzers, nicht an der Trägheit der Räume geprüft. Ein Wechsel pro Minute am Zyklus (60 s) ist die
   Auflösung.
4. **Anstieg „mehr als die Schrittweite“:** Die Geräte melden in 0,5-K-Schritten. Bei der Schrittweite 0,5 löst erst ein Anstieg um 1,0 den
   frühen Wechsel aus, ein Anstieg um genau 0,5 nicht. Das folgt dem Wortlaut des Nutzers.
5. **Lernen der Leistung je Gerät:** wird beim Wechselbetrieb kaum noch beobachtet, weil fast immer eine Übergabe läuft (die Beobachtung wird
   dann verworfen). Mögliche Auswege: Beobachtung nur über die Zahl der Geräte, ohne Rücksicht auf die Übergabe, oder Schätzung aus allen
   Zyklen (rekursive kleinste Quadrate).
6. **Anlaufschwelle im Kühlbetrieb:** gespiegelt angenommen (Sollwert Anlaufabstand über der Anzeige). Ob ein Gerät an der Decke beim
   Kühlen so anläuft, ist nicht gemessen.
7. **Rückführung auf die Messung** (Absenken, wenn die Außenleistung dauerhaft über der Anforderung liegt): Vorschlag, noch nicht
   freigegeben.
8. **Lernrate** und Ausreißergrenzen für `p_i`: wie beim Lernen der Kapazität (erste drei Beobachtungen ersetzen den Startwert durch
   ihren Median, danach gleitend mit Anteil 0,2, höchstens ±25 % je Beobachtung).
