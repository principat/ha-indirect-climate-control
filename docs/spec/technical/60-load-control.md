# 60 Lastregelung über Temperaturereignisse (Konzept, nicht umgesetzt)

Status: **Vorschlag zur Freigabe**, Stand 24.10.2026. Grundlage: FR-LOAD-01 (Fachspec, Status Vorschlag) und die Vorgaben des
Nutzers aus diesem Gespräch. Der Vorschlag in der Fachspec (fester 5-Minuten-Mittelwert, feste Wartezeit von 2 Minuten, beide
Richtungen gleichberechtigt) trägt nicht und wird nach der Freigabe ersetzt.

## Warum keine festen Zeitfenster

Erreicht ein Innengerät seinen Zielwert, zieht es keine Leistung mehr. Die Last am Außengerät fällt, wird aber verzögert
gemessen. Ein Regler mit festem Fenster merkt es erst, wenn das Außengerät schon ausgeht und unnötig taktet. Das Ereignis, auf das
es ankommt, ist die Änderung der Gerätetemperatur (0,5-K-Schritte). Die Anlage reagiert nicht synchron darauf, deshalb braucht der
Regler ein Gedächtnis dafür, welche Last ein Schritt bewirkt.

## Vorgaben des Nutzers

- **Ein Schritt verstellt zwei Geräte** (wie die bisherige Lastführung: eines der größeren, eines der kleineren Leistungsklasse).
- **Nachregeln nach oben und nach unten.** Absenken nur, solange die Anlage über der Mindeststufe liegt oder mehr als zwei Geräte
  gesteuert werden. Wird die geplante Leistung zurückgefahren, wird nachgeregelt, aber **nicht unter zwei Leistungsschritte**,
  vorzugsweise auf zwei Geräte verteilt (Mindeststufe).
- **Totband bleibt: 10 % von Pmin** um die angeforderte Leistung.
- **Bezug ist die angeforderte Leistung** (mindestens Pmin im Betrieb, FR-PLAN-03), nicht die reine Planleistung.
- **Reihenfolge:** zuerst der Sollwert (bis zur absoluten Grenze des Raums, nach unten bis Gerätetemperatur + 0), dann die Zahl der
  Geräte.
- **Zurücksetzen** beim Stopp der Anlage und beim Wechsel der Betriebsart auf den Standard.
- **Last je Leistungsschritt wird je Innengeräte-Leistungsklasse bestimmt.** Ein 1,6-kW-Gerät zieht weniger als ein 2,8-kW-Gerät. Die
  Lüfterstufe ist vermutlich relevant und gehört deshalb mit in den Schlüssel.

## Mechanismus (Vorschlag)

1. **Lücke je bedientem Gerät:** `g = Zielwert − Gerätetemperatur` in der Einheit der Anlage. Das Gerät zieht Leistung, solange `g`
   über null liegt. Der Regelzyklus führt den Zielwert bereits nach (Gerätetemperatur + Offset), die Lastregelung verändert den Offset
   je Gerät in Schritten seiner Schrittweite (`step`, optional je Innengerät, Standard 0,5 der Temperatureinheit).
2. **Erwartete Last** `P_erw = Σ p(Klasse, Lüfterstufe) × Schritte_i` über alle bedienten Geräte, mit dem gelernten `p`. Die
   Rechnung wird bei jedem Ereignis neu gemacht: Änderung der Gerätetemperatur eines bedienten Geräts, Änderung des Plans, Start oder
   Stopp eines Geräts. Es gibt kein festes Fenster.
3. **Entscheidung:** Liegt `P_erw` mehr als das Totband unter der angeforderten Leistung, werden zwei Geräte um je einen Schritt
   angehoben (Gerät mit der größten Leistungsklasse und eines mit der kleinsten, bei Gleichstand nach Abweichung). Liegt `P_erw`
   mehr als das Totband darüber und bleiben mindestens zwei Schritte (Mindeststufe), werden die zuletzt angehobenen Geräte um einen
   Schritt zurückgenommen.
4. **Gelernt wird `p`:** Nach jeder Verstellung wird die Änderung der gemessenen Außenleistung beobachtet, sobald sie sich beruhigt hat
   (Änderungsrate unter einer Schwelle, mit einer Obergrenze für die Wartezeit, nicht mit einem festen Fenster). Die gemessene
   Änderung wird auf die verstellten Schritte aufgeteilt und fließt als gleitender Wert in `p(Klasse, Lüfterstufe)` ein. Ausreißer
   (zum Beispiel ein anderes Gerät, das gleichzeitig ein- oder ausschaltet) werden verworfen. Die Werte bleiben über Neustarts erhalten
   und sind in der Diagnose sichtbar.
5. **Startwerte** gelten, bis genug Messungen vorliegen: noch offen (siehe unten).

## Erster Blick auf die vorhandenen Daten (ungeprüft)

Der Verlauf der Außenleistung vom 23.10.2026, 11:12 bis 13:58 Uhr (Recorder, 750 Werte), zeigt ein wiederkehrendes Muster: Etwa alle
25 bis 30 Minuten springt die Leistung binnen 30 bis 60 Sekunden von rund 1,0 kW auf 1,9 bis 2,1 kW und fällt innerhalb von 1 bis
1,5 Minuten wieder auf 0,85 bis 1,0 kW. Dazwischen schwankt sie in einem Takt von etwa 5 Minuten zwischen 0,95 und 1,3 kW. Die
Sprünge fallen vermutlich mit den Rampenschritten der alten Lastführung zusammen (Lastgrenze 1350 W), das ist **nicht belegt**, weil
die zugehörigen Sollwertänderungen nicht gegengeprüft sind. Sicher ist nur: Die Außenleistung reagiert innerhalb von Sekunden bis
einer Minute auf einen Anstoß und klingt in wenigen Minuten ab. Die Reaktionszeit und die Leistung je Schritt und Klasse müssen vor
der Umsetzung aus den Sollwertänderungen der Geräte gemessen werden.

## Offen vor der Umsetzung

1. **Startwerte** für `p(Klasse, Lüfterstufe)`: aus einer Auswertung deiner Daten (Referenzfall) oder eine allgemeine Annahme (zum
   Beispiel ein fester Anteil der Nennleistung je Schritt)?
2. **Lüfterstufe im Schlüssel:** Die Integration setzt die Lüfterstufe nicht, sie liest sie nur (`fan_mode` der Klima-Entität, steht
   schon in der Aufzeichnung). Soll `p` je gemeldeter Stufe gelernt werden, oder reicht zunächst eine Leistung je Klasse?
3. **Beruhigungskriterium** für das Lernen: Änderungsrate der Außenleistung unter einer Schwelle (in W je Minute), Obergrenze der
   Wartezeit (Vorschlag 10 Minuten). Die Zahlen sollen aus der Auswertung kommen.
4. **Fachspec:** FR-LOAD-01 wird auf diese Beschreibung umgestellt (Ereignisse statt Zeitfenster, Mindeststufe, Lernen je Klasse), die
   Parameter „Wartezeit 2 min" und „Lastmittel 5 min" entfallen.
