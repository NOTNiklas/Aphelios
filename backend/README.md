# APHELIOS – Backend

Der Python-Kern von APHELIOS: ereignisgesteuerter Event-Bus, unabhängige Engines,
Plugin-Loader und FastAPI/WebSocket-API.

## Schnellstart

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp ../.env.example ../.env        # optional: ANTHROPIC_API_KEY eintragen
python -m aphelios
```

Läuft auf `http://127.0.0.1:8787` – Health-Check: `curl http://127.0.0.1:8787/health`.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Struktur

```
aphelios/
├── core/       Event-Bus, BaseEngine, Manager, Config, SecurityGate
├── engines/    SystemEngine, ConversationEngine, MemoryEngine (+ Stubs)
├── plugins/    Plugin-Basisklasse + Loader
└── api/        FastAPI + WebSocket-Server
```

Details zur Gesamtarchitektur: siehe [`../ARCHITECTURE.md`](../ARCHITECTURE.md).
