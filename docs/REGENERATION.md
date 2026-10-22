# Projekt aus den fachlichen Spezifikationen neu erzeugen

Ziel: Bei geänderten technischen Gegebenheiten (neue Home-Assistant-Version, anderer Planer, anderes Gerät)
wird das Projekt komplett neu erzeugt. Alte technische Spezifikationen, alter Code und alte Tests
werden dabei nicht übernommen.

## Eingaben (bleiben)

- `docs/spec/functional/` (Quelle der Wahrheit)
- `docs/environment/` (aktuelle Rahmenbedingungen, vorher prüfen und aktualisieren)
- `config/` (Instanzdaten des Referenzfalls)
- `AGENTS.md`, `scripts/check_*.py`, `.releaserc.json`, `.devcontainer/` (Werkzeuge und Prozess)

## Wird verworfen und neu erzeugt

- `docs/spec/technical/`
- `custom_components/`, `tests/`

## Ablauf

1. Neuen Branch anlegen (`git switch -c regen/<datum>`).
2. `docs/environment/` auf aktuellen Stand bringen (Versionen, Geräteverhalten).
3. `docs/spec/technical/` und `custom_components/` und `tests/` löschen (nur der Branch, Git behält die Historie).
4. Technische Spezifikation neu schreiben, ausschließlich aus Fachspec + Rahmenbedingungen:
   Architektur, Schnittstellen, Datenmodell, Teststrategie. Danach committen (`docs:`).
5. Tests aus den Anforderungen ableiten (jede Anforderung mit `@pytest.mark.req`), erst rot committen (`test:`).
6. Code erzeugen, bis alles grün ist: unit, integration, e2e, Traceability, Lint.
7. Pull Request. Release läuft nach dem Merge automatisch.

## Prompt für Codex

> Lies `AGENTS.md`, `docs/REGENERATION.md`, alles unter `docs/spec/functional/`, `docs/environment/` und `config/`.
> Verwende die alte technische Spezifikation, den alten Code und die alten Tests nicht (sie sind gelöscht).
> Führe die Schritte 4 bis 6 aus. Frage nach, wenn eine fachliche Anforderung mehrdeutig ist,
> und ändere die Fachspec nicht ohne meine Freigabe.
