# 60 Lastregelung über Temperaturereignisse (Konzept, nicht umgesetzt)

Status: **Vorschlag zur Freigabe**, Stand 24.10.2026. Grundlage sind FR-LOAD-01 und FR-LOAD-02 (Fachspec, Status Vorschlag) und die
Vorgaben des Nutzers aus diesem Gespräch. Umsetzung steht aus.

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
- **Reihenfolge:** zuerst der Sollwert (bis zur absoluten Grenze des Raums, nach unten bis Gerätetemperatur + 0), dann die Zahl der
  Geräte.
- **Zurücksetzen** beim Stopp der Anlage und beim Wechsel der Betriebsart auf den Standard.
- **Die Leistungsänderung je Schritt wird je Innengerät gelernt.** Ein 1,6-kW-Gerät zieht weniger als ein 2,8-kW-Gerät. Die
  Lüfterstufe braucht keinen eigenen Schlüssel, sie steckt in der gelernten Geräteleistung. Eine Änderung der Lüfterleistung würde
  den Komfort beeinflussen und kommt deshalb als Stellgröße nicht in Frage.
- **Startwert je Gerät:** (Pmax − Pmin) geteilt durch die doppelte Zahl der Innengeräte. Die Leistung verteilt sich damit über die
  Geräte, der Anteil ist aber überschätzt, die Hälfte lässt dem Gerät eine Reserve.

## Mechanismus (Vorschlag)

1. **Lücke je bedientem Gerät:** `g = Zielwert − Gerätetemperatur` in der Einheit der Anlage. Das Gerät zieht Leistung, solange `g`
   über null liegt. Der Regelzyklus führt den Zielwert bereits nach (Gerätetemperatur + Offset), die Lastregelung verändert den Offset
   je Gerät in Schritten seiner Schrittweite (`step`, optional je Innengerät, Standard 0,5 der Temperatureinheit).
2. **Erwartete Last** `P_erw = Σ p_i × Schritte_i` über alle bedienten Geräte, mit dem gelernten `p_i` je Gerät. Die Rechnung wird bei
   jedem Ereignis neu gemacht: Änderung der Gerätetemperatur eines bedienten Geräts, Änderung des Plans, Start oder Stopp eines
   Geräts. Es gibt kein festes Fenster.
3. **Entscheidung:** Liegt `P_erw` mehr als das Totband unter der angeforderten Leistung, werden zwei Geräte um je einen Schritt
   angehoben (Gerät der größten Leistungsklasse und eines der kleinsten, bei Gleichstand nach Abweichung). Liegt `P_erw` mehr als das
   Totband darüber und bleiben mindestens zwei Schritte (Mindeststufe) oder mehr als zwei gesteuerte Geräte, werden die zuletzt
   angehobenen Geräte um einen Schritt zurückgenommen.
4. **Gelernt wird `p_i`:** Nach jeder Verstellung wird die Änderung der gemessenen Außenleistung beobachtet, sobald sie sich beruhigt
   hat (Änderungsrate unter einer Schwelle, mit einer Obergrenze für die Wartezeit, nicht mit einem festen Fenster). Die gemessene
   Änderung wird auf die gleichzeitig verstellten Schritte aufgeteilt und fließt als gleitender Wert in `p_i` der betroffenen Geräte
   ein. Ausreißer (zum Beispiel ein anderes Gerät, das gleichzeitig ein- oder ausschaltet, Betriebsartwechsel) werden verworfen. Die
   Werte bleiben über Neustarts erhalten und sind in der Diagnose sichtbar, nicht änderbar.
5. **Startwert** `p_i = (Pmax − Pmin) / (2 × Zahl der Innengeräte)`. Beispiel: Pmax 3,3 kW, Pmin 1,3 kW, 7 Geräte: 2,0 / 14 = 0,14 kW je
   Schritt und Gerät.

### Anmerkung zum Startwert

Die Formel unterschätzt vermutlich, was ein Schritt bewirkt, wenn man die einzelne Beobachtung vom 23.10. nimmt (siehe unten):
Zwei Schritte brachten kurzzeitig rund 0,9 kW, das wären 0,45 kW je Schritt. Das ist aber ein Spitzenwert, der binnen
anderthalb Minuten wieder abklang, der beruhigte Wert je Schritt ist unbekannt und wird erst gemessen. Ein zu kleiner Startwert führt
dazu, dass der Regler anfangs mehr Schritte macht als nötig, die Anlage zieht dann etwas mehr als angefordert. Ein zu großer führt
zu zu wenigen Schritten und damit zu Unterschreitung und Takten. Die Formel liegt also auf der unkritischen Seite, solange der
gelernte Wert nach wenigen Verstellungen übernimmt. Ein anderer Vorschlag ist nicht nötig.

## Erster Blick auf die vorhandenen Daten (ungeprüft)

Der Verlauf der Außenleistung vom 23.10.2026, 11:12 bis 13:58 Uhr (Recorder, 750 Werte), zeigt ein wiederkehrendes Muster: Etwa alle
25 bis 30 Minuten springt die Leistung binnen 30 bis 60 Sekunden von rund 1,0 kW auf 1,9 bis 2,1 kW und fällt innerhalb von 1 bis
1,5 Minuten wieder auf 0,85 bis 1,0 kW. Dazwischen schwankt sie in einem Takt von etwa 5 Minuten zwischen 0,95 und 1,3 kW. Die
Sprünge fallen vermutlich mit den Rampenschritten der alten Lastführung zusammen (Lastgrenze 1350 W), das ist **nicht belegt**, weil
die zugehörigen Sollwertänderungen nicht gegengeprüft sind. Sicher ist nur: Die Außenleistung reagiert innerhalb von Sekunden bis
einer Minute auf einen Anstoß und klingt in wenigen Minuten ab.

## Offen vor der Umsetzung

1. **Beruhigungskriterium** für das Lernen: Änderungsrate der Außenleistung unter einer Schwelle (W je Minute) und Obergrenze der
   Wartezeit (Vorschlag 10 Minuten). Die Zahlen sollten aus den Messwerten kommen, bis dahin Annahmen.
2. **Lernrate** und Ausreißergrenzen für `p_i`: Vorschlag wie beim Lernen der Kapazität (erste drei Beobachtungen ersetzen den
   Startwert durch ihren Median, danach gleitend mit Anteil 0,2, höchstens ±25 % je Beobachtung).
