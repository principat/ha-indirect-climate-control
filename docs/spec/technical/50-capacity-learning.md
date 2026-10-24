# 50 Pufferkapazität aus Betriebsdaten lernen (Konzept, nicht umgesetzt)

Status: **Vorschlag zur Freigabe**, überarbeitet am 24.10.2026 nach den Vorgaben des Nutzers (kurze Messzeiten,
Energie je 0,1 K, Wände vernachlässigt, Mindestfenster 0,35 K, Kühlen im Sommer, Leistungssensor als Pflicht).
Bis dahin gilt ein fester Startwert von 3 kWh_el/K (`DEFAULT_CAPACITY_KWH_PER_K` im Adapter, nicht im Kern). Die
Kapazität ist keine Einstellung.

## Ziel

Die Pufferkapazität soll sich aus dem Betrieb selbst einstellen, **schnell genug für Übergangszeit, Winter und
Sommer**. Gemessen wird nur im Heiz- bzw. Kühlbetrieb. Eine Ruhephase als Gegenstück entfällt.

## Größe

**E₀,₁ = elektrische Energie (kWh_el), die nötig ist, um die flächengewichtete mittlere Gerätetemperatur um 0,1 K
zu ändern.** Daraus folgt alles Weitere:

- Kapazität je Kelvin: `C = 10 × E₀,₁` (kWh_el/K)
- Kapazität für den Planer: `C × Breite der SOC-Skala` (wie bisher, derzeit 15 K)
- Startwert: E₀,₁ = 0,3 kWh_el (entspricht 3 kWh_el/K)

## Auflösung der Messung und Messfenster

Die Geräte melden in 0,5-K-Schritten. Der flächengewichtete Mittelwert springt deshalb bei jeder Änderung eines
Raums um `0,5 K × Flächenanteil`: bei den großen Räumen (je etwa 26 % der Fläche) um **0,13 K**, bei 12-m²-Räumen um
0,05 K. Die Auflösung liegt also in der Größe des Zielwerts von 0,1 K. Eine einzelne 0,1-K-Probe ist deshalb zu
ungenau (Fehler bis ±100 %). Das Einschwingen (Mittelwert über mehrere Proben) mildert das nur, es behebt es nicht.

**Vorgabe: Jede Schätzung beruht auf einem Fenster von mindestens 0,35 K.** Der Fehler stammt nur von den beiden
Enden des Fensters, höchstens ±0,13 K, also im ungünstigen Fall ±37 %, typisch etwa ±20 %.

Damit es trotzdem schnell geht, ist das Fenster **gleitend**: Nach jedem weiteren 0,1-K-Schritt der Mitteltemperatur
wird neu geschätzt, mit dem Verhältnis der Summen `ΣE / ΣΔT` über die letzten mindestens 0,35 K. Eine erste Schätzung
braucht beim Startwert 1,05 kWh_el, das sind **etwa 19 Minuten bei 3,3 kW und 48 Minuten bei Pmin (1,3 kW)**. Jede
weitere Schätzung folgt nach einem 0,1-K-Schritt, also etwa alle 14 Minuten bei Pmin und alle 6 Minuten bei 3,3 kW.
Die Schätzungen eines gleitenden Fensters sind nicht unabhängig, das Einschwingen (siehe unten) gewichtet deshalb nach
der Länge des Fensters.

Mögliche Verfeinerung (nicht Teil des Vorschlags): Der Zeitpunkt, an dem sich die Anzeige eines Raums um 0,5 K ändert,
markiert einen bekannten Wert. Interpoliert man zwischen diesen Zeitpunkten, sinkt der Fehler der Mitteltemperatur
deutlich und ein kürzeres Fenster wird möglich.

## Messung beim Heizen

Ein Fenster läuft, solange die Anlage heizt (`running`, mindestens eine Minute alt).

1. Beim Start werden die mittlere Gerätetemperatur `T_ref` und die bisher aufgenommene elektrische Energie `E_ref`
   des Außengeräts gemerkt.
2. Bei jeder Änderung der Mitteltemperatur um 0,1 K gegenüber dem letzten Schritt wird `ΔT = T − T_ref` und
   `E = E_ist − E_ref` fortgeschrieben, sobald `ΔT ≥ 0,35 K` ist, entsteht die Schätzung
   `E₀,₁ = E / ΔT × 0,1`. Ältere Schritte fallen am Fensteranfang weg, sodass `ΔT` bei etwa 0,35 K bleibt.
3. Das Fenster wird verworfen, wenn die Anlage stoppt oder in den Rückfall geht, ein Fenster geöffnet wird oder sich
   die Zahl der beteiligten Räume ändert.

## Kühlen (Sommer)

- Im Kühlbetrieb gilt dasselbe Verfahren mit **umgekehrtem Vorzeichen**: elektrische Energie je 0,1 K *Absenkung*
  der mittleren Gerätetemperatur, ebenfalls in Fenstern von mindestens 0,35 K.
- Es wird ein **eigener Wert** `E₀,₁(kühlen)` gelernt und getrennt gespeichert. Die Leistungszahl und der latente Anteil
  beim Kühlen unterscheiden sich vom Heizen, ein gemeinsamer Wert wäre falsch. Entfeuchten zählt nicht, es senkt die
  Temperatur kaum.
- Der Wärmeeintrag (Sonne, Außenluft) wirkt im Sommer gegen das Kühlen. Er steckt wie der Verlust im Winter in der
  gemessenen Energie, siehe nächster Abschnitt.
- **Offen in der Spec:** Kühlen kommt bisher nur als Schutz vor (FR-SAFE-03, Überhitzung). Soll es im Sommer wie das
  Heizen **geplant** werden (Kältespeicher mit gespiegelter SOC-Skala und gespiegelten Grenzen), braucht es eine neue
  Anforderung, dazu eine Betriebsart je Jahreszeit (Heizen oder Kühlen), weil beides nicht gleichzeitig laufen darf
  (FR-MODE-01). Das Lernen für das Kühlen ist erst sinnvoll, wenn das entschieden ist.

## Wände und Verluste

- Die langsame Auskühlung der Wände wird **vernachlässigt**. Ihr träger Puffer hält den Raum und wird beim Heizen
  wieder gefüllt. Darum braucht die Messung keine Gegenphase.
- **Verlust nach außen während des Fensters.** Die gemessene Energie `E` ist die Summe aus zwei Anteilen: dem Anteil,
  der den Puffer füllt (`C × ΔT`), und dem Anteil, der im selben Zeitraum nur den Wärmeverlust des Hauses ausgleicht.
  Der zweite Anteil hebt die Temperatur nicht und lässt E₀,₁ zu groß erscheinen. Beispiel: Heizt die Anlage mit
  1,3 kW und liegt der Bedarf bei 0,375 kW (deine Prognose, Tagesmittel), gehen 29 % der Energie in den Ausgleich des
  Verlusts. Der gelernte Wert wäre dann um etwa 40 % zu hoch (3,0 statt 2,1 kWh_el/K).
- **Vorschlag, noch offen:** Ist die Lastprognose der HAEO-Last am Knoten Klima als Sensor angegeben, wird ihr
  Integral über das Fenster abgezogen (`E_netto = E − ∫ P_Last dt`). Ohne Sensor bleibt der Wert unkorrigiert und damit
  eher zu groß. Im Sommer wäre es der Wärmeeintrag, falls die Prognose ihn liefert.
- Die Grundleistung im Lüften (Außengerät und Lüfter, etwa 35 W) wird als gemessene Leerlaufleistung abgezogen.

## Plausibilität und Aktualisierung

- Eine Schätzung gilt, wenn `E₀,₁` zwischen 0,03 und 3 kWh_el liegt (0,3 bis 30 kWh_el/K) und das Fenster mindestens
  60 s lief.
- Schnelles Einschwingen: Die ersten drei gültigen Schätzungen mit disjunkten Fenstern ersetzen den Startwert durch ihren
  Median. Danach `E_neu = E_alt + 0,2 × w × (Schätzung − E_alt)`, `w` = Fensterlänge in Kelvin geteilt durch 0,35 (höchstens 1),
  je Schätzung höchstens ±25 % Änderung. So folgt die Kapazität einem Wechsel der Jahreszeit (und der Leistungszahl)
  innerhalb von Stunden.
- Der gelernte Wert und die Zahl der Schätzungen werden dauerhaft gespeichert und bleiben über Neustarts erhalten.
- Sichtbar als Sensor „Gelernte Kapazität“ mit den Attributen Schätzungen und letzte Aktualisierung (für Heizen und
  Kühlen je ein Sensor). Ein Dienst setzt auf den Startwert zurück.

## Benötigte Eingänge

- **Elektrische Leistung des Außengeräts (Sensor, W): Pflichtangabe der Anlage.** Seit 0.6 Pflichtfeld bei der Einrichtung,
  bei älteren Einträgen erinnert eine Reparaturmeldung daran. Der Sensor dient dem Vergleich mit der geplanten Leistung
  und dem Lernen. Im Referenzfall `sensor.klima_aussen_leistung_w`. Frühere Daten sind unbrauchbar, wenn der Sensor
  Scheinleistung lieferte.
- Optional: Lastprognose der HAEO-Last (Sensor) für die Korrektur des Verlusts.
- Vorhanden: Gerätetemperaturen, Betriebszustand, Fensterkontakte, Flächen.

## Offene Fragen zur Freigabe

1. Soll der Verlust über die Lastprognose abgezogen werden (genauer, aber ein weiteres Feld), oder genügt der
   unkorrigierte Wert?
2. Soll Kühlen im Sommer als geplanter Betrieb eingeführt werden (gespiegelter SOC, Betriebsart je Jahreszeit)? Davon
   hängt ab, ob das Lernen für das Kühlen jetzt oder später umgesetzt wird.
3. Soll der Nutzer den gelernten Wert sehen und zurücksetzen können, oder nur das System?

## Vorschlag für die Fachspec (nach Freigabe)

| ID | Anforderung | Status | Ebenen |
| --- | --- | --- | --- |
| FR-PLNR-02 | Die Pufferkapazität wird aus der elektrischen Energie je 0,1 K Änderung der mittleren Gerätetemperatur im Heiz- und im Kühlbetrieb laufend angepasst, ausgehend von einem Startwert. Jede Schätzung beruht auf einer Änderung von mindestens 0,35 K. Sie ist keine Einstellung. Der gelernte Wert bleibt über Neustarts erhalten. | Vorschlag | unit,integration |
