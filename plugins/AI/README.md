# Plugin-Kategorie: AI

Routet Anfragen an verschiedene AI-Modelle.

Plugins dieser Kategorie liegen jeweils in einem eigenen Unterordner mit einer
`manifest.json`. Als Vorlage dient `manifest.example.json` in diesem Ordner.

## Beispiel

```
plugins/AI/
└── model-router/
    ├── manifest.json      # von manifest.example.json ableiten (enabled: true)
    └── plugin.py          # Klasse `Plugin`, erbt von aphelios.plugins.base.Plugin
```

Details zum Plugin-System: siehe [`../../docs/plugins.md`](../../docs/plugins.md).
