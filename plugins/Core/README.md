# Plugin-Kategorie: Core

System-Kernfunktionen und Health-Signale.

Plugins dieser Kategorie liegen jeweils in einem eigenen Unterordner mit einer
`manifest.json`. Als Vorlage dient `manifest.example.json` in diesem Ordner.

## Beispiel

```
plugins/Core/
└── core-heartbeat/
    ├── manifest.json      # von manifest.example.json ableiten (enabled: true)
    └── plugin.py          # Klasse `Plugin`, erbt von aphelios.plugins.base.Plugin
```

Details zum Plugin-System: siehe [`../../docs/plugins.md`](../../docs/plugins.md).
