# 50 Pufferkapazität aus Betriebsdaten lernen (Konzept, nicht umgesetzt)

Status: **Vorschlag zur Freigabe**, überarbeitet am 24.10.2026 nach den Vorgaben des Nutzers (kurze Messzeiten,
Energie je 0,1 K, Wände vernachlässigt). Bis dahin gilt ein fester Startwert von 3 kWh_el/K
(`DEFAULT_CAPACITY_KWH_PER_K` im Adapter, nicht im Kern). Die Kapazität ist keine Einstellung.

## Ziel

Die Pufferkapazität soll sich aus dem Betrieb selbst einstellen, **schnell genug für Übergangszeit, Winter und
Sommer**. Gemessen wird nur im Heizbetrieb, in Fenstern von wenigen Minuten. Eine Ruhephase als Gegenstück entfällt.

## Größe

**E₀,₁ = elektrische Energie (kWh_el), die nötig ist, um die flächengewichtete mittlere Gerätetemperatur um 0,1 K
anzuheben.** Daraus folgt alles Weitere:

- Kapazität je Kelvin: `C = 10 × E₀,₁` (kWh_el/K)
- Kapazität für den Planer: `C × Breite der SOC-Skala` (wie bisher, derzeit 15 K)
- Startwert: E₀,₁ = 0,3 kWh_el (entspricht 3 kWh_el/K)

0,1 K ist die richtige Schrittweite: Die Geräte melden in 0,5-K-Schritten, der flächengewichtete Mittelwert über
mehrere Räume ändert sich dadurch in Schritten von etwa 0,07 K und ist damit fein genug, um 0,1 K zu erkennen.

## Messung (nur im Heizbetrieb)

Ein Messfenster läuft, solange die Anlage in Betrieb ist (`running`, mindestens eine Minute alt).

1. Beim Start des Fensters werden die mittlere Gerätetemperatur `T_ref` und die bisher aufgenommene elektrische
   Energie `E_ref` des Außengeräts gemerkt.
2. Sobald die mittlere Temperatur um mindestens 0,1 K über `T_ref` liegt, entsteht eine Probe
   `E₀,₁ = (E − E_ref) / (T − T_ref) × 0,1`. Danach beginnt das nächste Fenster ohne Pause.
3. Das Fenster wird verworfen, wenn die Anlage stoppt oder in den Rückfall geht, ein Fenster offen ist oder sich die
   Zahl der beteiligten Räume ändert. Dann wird `T_ref`/`E_ref` neu gesetzt.

Dauer eines Fensters beim Startwert (0,3 kWh_el je 0,1 K): etwa **14 Minuten bei Pmin (1,3 kW)** und **unter
8 Minuten bei 2,5 kW**. Die Mindestlaufzeit von 10 Minuten reicht damit für mindestens eine Probe je Lauf. Das Konzept
davor brauchte 45 Minuten je Heizphase plus mindestens 60 Minuten Ruhe.

## Wände und Verluste

- Die langsame Auskühlung der Wände wird **vernachlässigt**. Ihr träger Puffer hält den Raum und wird beim Heizen
  wieder gefüllt. Darum braucht die Messung keine Gegenphase.
- Der Wärmeverlust des Raums während des Fensters steckt dagegen in der gemessenen Energie und lässt E₀,₁ zu groß
  erscheinen. Bei Pmin (1,3 kW) und einem Bedarf von etwa 0,3 bis 0,6 kW wäre das ein spürbarer Anteil. **Vorschlag:**
  Ist die Lastprognose der HAEO-Last am Knoten Klima als Sensor angegeben, wird ihr Integral über das Fenster
  abgezogen (`E_netto = E − ∫ P_Last dt`). Ohne Sensor bleibt der Wert unkorrigiert und damit eher zu groß.
- Die Grundleistung im Lüften (Außengerät und Lüfter, etwa 35 W) wird als gemessene Leerlaufleistung abgezogen.

## Plausibilität und Aktualisierung

- Eine Probe gilt, wenn `E₀,₁` zwischen 0,03 und 3 kWh_el liegt (0,3 bis 30 kWh_el/K) und das Fenster mindestens
  60 s lief.
- Schnelles Einschwingen: Die ersten fünf gültigen Proben ersetzen den Startwert durch ihren Median. Danach
  `E_neu = E_alt + 0,2 × (Probe − E_alt)`, je Probe höchstens ±25 % Änderung. Damit folgt die Kapazität einem
  Wechsel der Jahreszeit (und der Leistungszahl) innerhalb von Stunden.
- Der gelernte Wert und die Zahl der Proben werden dauerhaft gespeichert und bleiben über Neustarts erhalten.
- Sichtbar als Sensor „Gelernte Kapazität“ mit den Attributen Proben und letzte Aktualisierung. Ein Dienst setzt
  auf den Startwert zurück.

## Benötigte Eingänge

- **Elektrische Leistung des Außengeräts (Sensor, W):** neu, optional. Im Referenzfall `sensor.klima_aussen_leistung_w`.
  Ohne ihn bleibt es beim Startwert. Frühere Daten sind unbrauchbar, wenn der Sensor Scheinleistung lieferte.
- Optional: Lastprognose der HAEO-Last (Sensor) für die Korrektur des Verlusts.
- Vorhanden: Gerätetemperaturen, Betriebszustand, Fensterkontakte, Flächen.

## Offene Fragen zur Freigabe

1. Soll der Verlust über die Lastprognose abgezogen werden (genauer, aber ein weiteres Feld), oder genügt der
   unkorrigierte Wert?
2. Soll der Leistungssensor des Außengeräts Pflicht werden oder optional bleiben (dann ohne Lernen)?
3. Soll der Nutzer den gelernten Wert sehen und zurücksetzen können, oder nur das System?

## Vorschlag für die Fachspec (nach Freigabe)

| ID | Anforderung | Status | Ebenen |
| --- | --- | --- | --- |
| FR-PLNR-02 | Die Pufferkapazität wird aus der elektrischen Energie je 0,1 K Änderung der mittleren Gerätetemperatur im Heizbetrieb laufend angepasst, ausgehend von einem Startwert. Sie ist keine Einstellung. Der gelernte Wert bleibt über Neustarts erhalten. | Vorschlag | unit,integration |
