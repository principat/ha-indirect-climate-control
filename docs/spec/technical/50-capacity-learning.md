# 50 Pufferkapazität aus Betriebsdaten lernen (Konzept, nicht umgesetzt)

Status: **Vorschlag zur Freigabe.** Bis dahin gilt ein fester Startwert von 7 kWh_el/K
(`DEFAULT_CAPACITY_KWH_PER_K` im Adapter, nicht im Kern). Die Kapazität ist keine Einstellung mehr.

## Ziel

Die Pufferkapazität C (elektrische Energie je Kelvin Raumtemperatur, kWh_el/K) soll sich aus der gemessenen
Leistung des Außengeräts und dem Temperaturverlauf der Räume selbst einstellen. Der Nutzer muss sie nicht
kennen. Der Planer erhält `Kapazität = C × Breite der SOC-Skala`.

## Modell

Vereinfachtes Einknotenmodell in elektrischen Äquivalenten:

    C · dT/dt = P_el − L

- T: flächengewichtete mittlere Gerätetemperatur aller aktiven Räume. Der Mittelwert über mehrere Geräte
  ist feiner aufgelöst als die ganzen Grad eines einzelnen Geräts.
- P_el: gemessene Wirkleistung des Außengeräts abzüglich der Lüfterleistung im neutralen Modus.
- L: Wärmeverlust in elektrischen Äquivalenten. Er ist unbekannt und hängt vor allem von der Außentemperatur ab.

## Schätzverfahren: gepaarte Phasen

L kürzt sich heraus, wenn eine Heizphase mit einer unmittelbar benachbarten Ruhephase verglichen wird, in der
der Verlust praktisch gleich ist (gleiche Tageszeit, wenige Stunden Abstand):

    Ruhephase:  C · s_aus = −L          (s_aus = Steigung dT/dt, negativ)
    Heizphase:  C · s_an  = P_an − L    (P_an = mittlere elektrische Leistung)
    ⇒           C = P_an / (s_an − s_aus)

Die Steigungen werden per linearer Regression über die Phase bestimmt, nicht aus Anfangs- und Endwert.

### Gültige Stichproben

- Ruhephase ≥ 60 min ohne Heizen und Kühlen, Heizphase ≥ 45 min mit stabiler Geräteauswahl.
- Abstand der beiden Phasen ≤ 3 h, keine offenen Fenster, kein Moduswechsel durch Konflikte, kein Rückfall.
- Differenz s_an − s_aus ≥ 0,5 K/h (sonst dominiert die Auflösung der Gerätetemperatur).
- Ergebnis plausibel: 1 bis 30 kWh_el/K.

### Aktualisierung

- Gleitender Mittelwert: `C_neu = C_alt + α · (C_probe − C_alt)` mit α = 0,1. Eine Stichprobe ändert C um höchstens 20 %.
- Der gelernte Wert und die Zahl der Stichproben werden dauerhaft gespeichert (überstehen Neustarts).
- Sichtbar als Sensor „Gelernte Kapazität“ mit den Attributen Stichproben und letzte Aktualisierung,
  zurücksetzbar per Dienst auf den Startwert.

## Benötigte Eingänge

- Neu: **Sensor Leistung Außengerät** (W), im Referenzfall `sensor.klima_aussen_leistung_w`. Ohne ihn bleibt C
  beim Startwert. Hinweis aus den Rahmenbedingungen: Vor dem 18.10.2026 14:30 lieferte der Shelly
  Scheinleistung; frühere Daten sind unbrauchbar.
- Vorhanden: Gerätetemperaturen, Modi, Fensterkontakte, Flächen.

## Offene Fragen zur Freigabe

1. Schnelle und langsame Kapazität (offener Punkt der Fachspec): Phasen von 1 bis 4 h messen vor allem Luft und
   Einrichtung, Wände reagieren langsamer. Vorschlag: Phasenlänge passend zum Planungsraster wählen und
   C zunächst als eine Größe führen.
2. Soll der Leistungssensor Pflicht werden oder optional bleiben (dann ohne Lernen)?
3. Soll ein Nutzer den gelernten Wert sehen und zurücksetzen können, oder nur das System?

## Vorschlag für die Fachspec (nach Freigabe)

| ID | Anforderung | Status | Ebenen |
| --- | --- | --- | --- |
| FR-PLNR-02 | Die Pufferkapazität wird aus gemessener Leistung und Temperaturverlauf laufend angepasst, ausgehend von einem Startwert. Sie ist keine Einstellung. Der gelernte Wert bleibt über Neustarts erhalten. | Vorschlag | unit,integration |
