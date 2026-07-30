# Plugin-Kategorie: Music

Steuert Spotify (Play/Pause/Skip/Lautstärke).

Plugins dieser Kategorie liegen jeweils in einem eigenen Unterordner mit einer
`manifest.json`. Als Vorlage dient `manifest.example.json` in diesem Ordner.

## Beispiel

```
plugins/Music/
└── spotify-control/
    ├── manifest.json      # von manifest.example.json ableiten (enabled: true)
    └── plugin.py          # Klasse `Plugin`, erbt von aphelios.plugins.base.Plugin
```

Details zum Plugin-System: siehe [`../../docs/plugins.md`](../../docs/plugins.md).
