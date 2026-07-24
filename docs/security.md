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
