# Sicherheit – SecurityGate

APHELIOS darf tief ins System eingreifen. Deshalb gilt: **keine gefährliche Aktion ohne
ausdrückliche Bestätigung.**

## Gefährliche Aktionen

Immer bestätigungspflichtig:

- Dateien löschen
- Registry ändern
- Programme deinstallieren
- Systemdateien ändern
- Passwörter anzeigen

## Funktionsweise

Das `SecurityGate` (`backend/aphelios/core/security.py`) klassifiziert jede angeforderte
Aktion nach Risiko:

| Stufe | Beispiel | Verhalten |
|---|---|---|
| `SAFE` | Stats lesen, Notiz schreiben | wird sofort ausgeführt |
| `CONFIRM` | Datei löschen, Programm starten | wartet auf Bestätigung |
| `DANGEROUS` | Registry, Systemdatei, Deinstallation | wartet auf explizite Bestätigung + Warnhinweis |

Ablauf für eine bestätigungspflichtige Aktion:

```
Engine ruft SecurityGate.request(action)
   │
   ├─ SAFE       → sofort erlaubt
   │
   └─ CONFIRM/DANGEROUS
        → publish("confirmation.request", {id, action, level, reason})
        → HUD zeigt Bestätigungsdialog
        → Nutzer bestätigt  → publish("confirmation.approve", {id})
        → Nutzer lehnt ab    → publish("confirmation.deny", {id})
        → ohne Antwort       → Aktion wird NICHT ausgeführt (deny-by-default)
```

## Prinzipien

1. **Deny by default** – ohne ausdrückliche Zustimmung passiert nichts.
2. **Transparenz** – jede Anfrage nennt Aktion, Stufe und Grund.
3. **Nachvollziehbarkeit** – Bestätigungen werden protokolliert (später über MemoryEngine).
4. **Least privilege** – Plugins deklarieren benötigte Rechte im Manifest.

## Verwendung in einer Engine

```python
allowed = await self.security.request(
    action="delete_file",
    target="C:/Users/…/alt.txt",
    level=RiskLevel.CONFIRM,
    reason="Nutzer bat darum, die Datei zu löschen.",
)
if allowed:
    ...  # Aktion ausführen
```

Seit Alpha 1.2 gibt es einen ersten echten Nutzer dieses Musters: die
`AutomationEngine` (`backend/aphelios/engines/automation_engine.py`) fragt
vor jeder Datei-Löschung/-Erstellung/-Verschiebung, jedem Programmstart und
jeder PowerShell-Ausführung genau so das SecurityGate – siehe
`docs/engines.md` für die konkreten Aktionen und Risikostufen.

Seit Alpha 1.4 gilt dasselbe für die `VisionEngine`
(`backend/aphelios/engines/vision_engine.py`): **jede** Bildschirmaufnahme
läuft über `CONFIRM`, auch die rein lokale OCR-Aktion (`/lies`), die nichts
an Claude schickt – ein Screenshot kann beliebig sensible Inhalte zeigen
(Passwörter in Eingabefeldern, private Nachrichten, andere Fenster), genau
wie „Passwörter anzeigen" oben explizit bestätigungspflichtig ist.

## Wichtige Falle: Bestätigung auf derselben WebSocket-Verbindung

`SecurityGate.request()` blockiert, bis `confirmation.approve`/`.deny` mit
passender `id` eintrifft. Kommt diese Bestätigung – wie beim HUD – über
**dieselbe** WebSocket-Verbindung zurück, die die ursprüngliche Anfrage
gesendet hat, darf der Server eingehende Nachrichten **nicht sequenziell
abwarten** (`await handle(message)` in einer Schleife) – sonst blockiert die
Verbindung sich selbst: Sie wartet auf die nächste Nachricht (die
Bestätigung), kann diese aber nie lesen, weil sie noch mit der vorherigen
"beschäftigt" ist. `backend/aphelios/api/server.py` plant deshalb jede
eingehende Nachricht als eigenen Task ein (`asyncio.create_task(...)`),
statt sie zu awaiten. Regressionstest: `backend/tests/test_ws_integration.py`.
