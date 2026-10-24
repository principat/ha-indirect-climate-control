# 60 Lastregelung über Temperaturereignisse

Status: **freigegeben und umgesetzt am 24.10.2026** (`core/load.py`, Anbindung in `controller.py` und `coordinator.py`). Grundlage
sind FR-LOAD-01 und FR-LOAD-02 und die Vorgaben des Nutzers aus diesem Gespräch. Das Konzept ist an Messwerten noch nicht geprüft.

## Warum keine festen Zeitfenster

Erreicht ein Innengerät seinen Zielwert, zieht es keine Leistung mehr. Die Last am Außengerät fällt, wird aber verzögert gemessen. Ein
Regler mit festem Fenster merkt es erst, wenn das Außengerät schon ausgeht und unnötig taktet. Das Ereignis, auf das es ankommt, ist
die Änderung der Gerätetemperatur (0,5-K-Schritte). Die Anlage reagiert nicht synchron darauf, deshalb braucht der Regler ein
Gedächtnis dafür, welche Last ein Schritt bewirkt.

## Vorgaben des Nutzers

- **Ein Schritt verstellt zwei Geräte** (wie die bisherige Lastführung: eines der größten, eines der kleinsten Leistungsklasse).
- **Nachregeln nach oben und nach unten.** Absenken nur, solange die Anlage über der Mindeststufe liegt oder mehr als zwei Geräte
  gesteuert werden. Wird die geplante Leistung zurückgefahren, wird nachgeregelt, aber **nicht unter zwei Leistungsschritte**,
  vorzugsweise auf zwei Geräte verteilt (Mindeststufe).
- **Totband bleibt: 10 % von Pmin** um die angeforderte Leistung.
- **Bezug ist die angeforderte Leistung** (mindestens Pmin im Betrieb, FR-PLAN-03), nicht die reine Planleistung.
- **Reihenfolge:** zuerst der Sollwert (bis zur absoluten Grenze des Raums), dann die Zahl der Geräte.
- **Zurücksetzen** beim Stopp der Anlage und beim Wechsel der Betriebsart auf den Standard.
- **Die Leistungsänderung je Schritt wird je Innengerät gelernt.** Ein 1,6-kW-Gerät zieht weniger als ein 2,8-kW-Gerät. Die
  Lüfterstufe braucht keinen eigenen Schlüssel, sie steckt in der gelernten Geräteleistung. Eine Änderung der Lüfterleistung würde
  den Komfort beeinflussen und kommt deshalb als Stellgröße nicht in Frage.
- **Anlauf (Messung des Nutzers):** Bei einem Sollwert von 20 °C läuft ein Gerät schon bei einer Anzeige von 22 °C an (Gerät an der
  Decke). Zwei Geräte mit je einem Schritt über dieser Schwelle bringen das Außengerät auf Pmin (etwa 1,3 kW elektrisch).
- **Startwert je Gerät** für Schritte über der Mindeststufe: (Pmax − Pmin) geteilt durch die doppelte Zahl der Innengeräte. Die
  Leistung verteilt sich damit über die Geräte, der Anteil ist aber überschätzt, die Hälfte lässt dem Gerät eine Reserve.

## Mechanismus

1. **Anlaufschwelle und Schritte.** Ein Innengerät an der Decke misst zu warm und läuft schon an, wenn seine Anzeige um den
   Anlaufabstand `start_offset` (Standard 2, je Innengerät, in der Einheit der Anlage) über dem Sollwert liegt, bei einem Sollwert von
   20 °C also bei 22 °C. Die Anlaufschwelle liegt daher beim Heizen **unter** der Gerätetemperatur: `Sollwert = Gerätetemperatur −
   Anlaufabstand + n × Schrittweite`, begrenzt durch die absolute Grenze des Raums. `n` sind die Leistungsschritte des Geräts, die
   Schrittweite `step` ist je Innengerät einstellbar (Standard 0,5). Im Kühlbetrieb gilt es gespiegelt (Annahme, nicht gemessen).
   Ein früherer Stand setzte den Sollwert auf Gerätetemperatur + n × Schrittweite, das waren schon 8 Schritte über der Schwelle und
   trieb die Leistung auf über 2 kW.
2. **Mindeststufe = Pmin.** Zwei Geräte mit je einem Schritt (Sollwert Gerätetemperatur − 1,5) fordern genug Leistung, damit das
   Außengerät mit etwa Pmin läuft. Die erwartete Last ist `0` ohne Schritt, `Pmin` bei höchstens zwei Schritten und darüber
   `Pmin + p̄ × (Σ Schritte − 2)`, mit `p̄` als nach Schritten gewichtetem Mittel der gelernten Leistung je Schritt der bedienten Geräte
   (`core/load.py: expected_load_w`). Die Rechnung wird bei jedem Ereignis neu gemacht: Änderung der Gerätetemperatur eines bedienten
   Geräts, Änderung des Plans, Start oder Stopp eines Geräts. Es gibt kein festes Fenster.
3. **Entscheidung:** Liegt die erwartete Last mehr als das Totband unter der angeforderten Leistung, werden zwei Geräte um je einen
   Schritt angehoben (Gerät der größten Leistungsklasse und eines der kleinsten, bei Gleichstand nach Abweichung). Liegt sie mehr als
   das Totband darüber und bleiben mindestens zwei Schritte (Mindeststufe) oder mehr als zwei gesteuerte Geräte, werden die zuletzt
   angehobenen Geräte um einen Schritt zurückgenommen.
4. **Gelernt wird `p_i`** nur oberhalb der Mindeststufe: Nach jeder Verstellung eines laufenden Außengeräts wird die Außenleistung
   beobachtet, bis sie sich beruhigt hat (siehe Beruhigung). Die gemessene Änderung geteilt durch die erwartete bestimmt einen Faktor,
   mit dem die Werte der beteiligten Geräte skaliert werden. Ein Lauf aus dem Stillstand erreicht nur die Mindeststufe (Pmin) und
   lehrt nichts. Beobachtungen, in die ein anderes Ereignis hineinspielt (andere Verstellung, Start oder Stopp eines Geräts,
   Betriebsartwechsel, Fenster, Raum unter Schutz), werden verworfen, ebenso solche unter dem halben Totband. Die Werte bleiben über
   Neustarts erhalten und sind in der Diagnose sichtbar, nicht änderbar.
5. **Startwert** `p_i = (Pmax − Pmin) / (2 × Zahl der Innengeräte)` je Schritt oberhalb der Mindeststufe. Beispiel: Pmax 3,3 kW, Pmin
   1,3 kW, 7 Geräte: 2,0 / 14 = 0,14 kW je Schritt und Gerät.

## Erster Blick auf die vorhandenen Daten (ungeprüft)

Der Lauf vom 24.10.2026, 21:01 bis 21:11 Uhr (Version 0.7.0, die Sollwerte lagen 2 K über der Gerätetemperatur), zeigte: Die
Außenleistung stand nach dem Start zweieinhalb Minuten bei etwa 1,22 kW und stieg dann auf 1,6 kW und 2,19 kW, obwohl nur 1,3 kW
angefordert waren. Erklärung des Nutzers: Das waren acht Schritte über der Anlaufschwelle für ein Gerät statt der zwei der Mindeststufe.
Die zuvor vermutete Ursache (der Verdichter baut bei konstantem Abstand weiter Leistung auf) ist damit nicht nötig. Vom 23.10. gibt es
außerdem einen Verlauf mit Sprüngen von 1,0 auf 1,9 bis 2,1 kW, der vermutlich zu den Rampenschritten der alten Lastführung gehörte
(nicht belegt).

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

## Offen (Annahmen, bis zur Prüfung an Messwerten)

1. **Lernrate** und Ausreißergrenzen für `p_i`: wie beim Lernen der Kapazität (erste drei Beobachtungen ersetzen den Startwert durch
   ihren Median, danach gleitend mit Anteil 0,2, höchstens ±25 % je Beobachtung).
2. **Anlaufschwelle im Kühlbetrieb:** gespiegelt angenommen (Sollwert Anlaufabstand über der Anzeige). Ob ein Gerät an der Decke beim
   Kühlen so anläuft, ist nicht gemessen.
3. **Rückführung auf die Messung** (Absenken, wenn die Außenleistung dauerhaft über der Anforderung liegt): Vorschlag, noch nicht
   freigegeben. Mit dem Anlaufabstand ist sie vielleicht unnötig, das zeigen die ersten Läufe.
4. **Verworfene Beobachtungen:** Das Konzept lernt nur aus sauberen Beobachtungen. Wenn zu viele verloren gehen, ist eine Schätzung
   über alle Ereignisse zusammen (rekursive kleinste Quadrate je Gerät) die Alternative.
