# Technische Spezifikation (abgeleitet, wegwerfbar)

Diese Dateien werden aus `docs/spec/functional/` und `docs/environment/` erzeugt. Sie sind keine Quelle der Wahrheit.
Bei geänderten technischen Gegebenheiten werden sie gelöscht und neu geschrieben (`docs/REGENERATION.md`).
Nichts hier in die Fachspec zurückschreiben.

Dateien:

- `10-architecture.md`: Aufbau, Schichten (Kern ohne Plattform, Adapter für die Plattform), Datenfluss.
- `20-interfaces.md`: Entitäten, Dienste, Konfigurationsablauf, Schnittstelle zum Planer.
- `30-testing.md`: Teststrategie je Ebene, Simulator für die Innengeräte, Aufbau der e2e-Instanz.
- `40-release.md`: Ablauf der Veröffentlichung.
- `70-operating-modes.md`: Betriebsmodi, Heizoffset, Taktoptimierung, Puffersteuerung, Lüfterstufe.
