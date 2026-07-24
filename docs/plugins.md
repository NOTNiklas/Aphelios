# Plugin-System

Jede erweiterbare Fähigkeit von APHELIOS kann als **Plugin** ergänzt werden, ohne den
Kern anzufassen. Plugins liegen in Kategorie-Ordnern unter `/plugins/` und werden beim
Start automatisch entdeckt.

## Ordnerstruktur

```
plugins/
├── Core/        Voice/       Memory/      Browser/
├── Windows/     Developer/   Office/      AI/
├── Automation/  Security/    Vision/      Music/
├── Calendar/    Mail/        HomeDesk/    SmartHome/
```

Jede Kategorie enthält ein `README.md` und eine `manifest.example.json`.

## Manifest

Ein Plugin wird durch eine `manifest.json` beschrieben:

```json
{
  "name": "spotify-control",
  "version": "0.1.0",
  "category": "Music",
  "entrypoint": "plugin.py:SpotifyPlugin",
  "description": "Steuert Spotify (Play/Pause/Skip/Lautstärke).",
  "permissions": ["network", "process"],
  "enabled": true
}
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `name` | ✅ | Eindeutiger Bezeichner |
| `version` | ✅ | SemVer |
| `category` | ✅ | Eine der Kategorien oben |
| `entrypoint` | ✅ | `datei.py:KlassenName` (erbt von `Plugin`) |
| `description` | ⬜ | Kurzbeschreibung |
| `permissions` | ⬜ | Angeforderte Rechte (`network`, `filesystem`, `process`, `registry`, …) |
| `enabled` | ⬜ | Standard `true` |

## Ein Plugin schreiben

```python
from aphelios.plugins.base import Plugin
from aphelios.core.event_bus import Event

class SpotifyPlugin(Plugin):
    async def on_load(self) -> None:
        self.bus.subscribe("music.play", self.play)

    async def play(self, event: Event) -> None:
        ...  # Spotify-API aufrufen
```

## Loader

`aphelios/plugins/loader.py` durchsucht die Kategorie-Ordner, liest jedes `manifest.json`,
validiert es gegen das Schema und instanziiert den Entry-Point. Ungültige oder
deaktivierte Plugins werden übersprungen und protokolliert.

> In Alpha 1.0 enthalten die Kategorie-Ordner nur Beispiel-Manifeste. Der Loader ist
> vollständig funktionsfähig und lädt Plugins, sobald echte `manifest.json`-Dateien
> vorhanden sind.
