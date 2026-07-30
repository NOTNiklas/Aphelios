"""End-to-End-Regressionstest für die WebSocket-Nachrichtenverarbeitung.

Deckt einen echten Deadlock ab, der beim Bau der AutomationEngine auffiel:
``EventBus.publish()`` wartet, bis alle Subscriber (inkl. Engine-Handler)
fertig sind. Ein Handler, der über das SecurityGate auf eine Bestätigung
wartet, wartet also auf die NÄCHSTE Nachricht auf genau derselben
WebSocket-Verbindung. Verarbeitet ``ws_endpoint`` eingehende Nachrichten
sequenziell (``await`` statt als Task einzuplanen), kann diese Bestätigung
nie ankommen – die Verbindung blockiert sich selbst, bis das SecurityGate
nach 120 Sekunden in ein Deny-by-default läuft.

Nutzt einen echten ``TestClient`` mit laufenden Engines (nicht nur isolierte
Unit-Tests), weil der Bug genau in der Interaktion zwischen WS-Endpoint und
EventBus liegt, nicht in einer einzelnen Komponente für sich.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aphelios.api.server import create_app
from aphelios.core.config import Config


def _next_message_with_topic(ws, topic: str, max_tries: int = 20) -> dict:
    """Liest WS-Nachrichten, bis eine mit passendem Topic kommt (überspringt
    z. B. periodische ``system.stats``-Broadcasts, die dazwischenfunken)."""
    for _ in range(max_tries):
        msg = ws.receive_json()
        if msg.get("topic") == topic:
            return msg["data"]
    raise AssertionError(f"Kein {topic!r} innerhalb von {max_tries} Nachrichten erhalten")


def test_confirmation_approval_on_same_connection_does_not_deadlock(tmp_path):
    # Regression: siehe Modul-Docstring. Vorher lief dieser Test in ein
    # 120-Sekunden-Timeout und endete mit "Abgelehnt" statt "Gelöscht".
    target = tmp_path / "loeschbar.txt"
    target.write_text("weg damit")

    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    app = create_app(config)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()  # Begrüßungs-Snapshot (engine.status)

        ws.send_json({"type": "chat", "id": "x1", "text": f"/loesche {target}"})
        confirmation = _next_message_with_topic(ws, "confirmation.request")

        # Genau diese Bestätigung muss auf DERSELBEN Verbindung ankommen,
        # während die Löschanfrage noch "offen" ist.
        ws.send_json({"type": "confirmation.approve", "id": confirmation["id"]})

        final = _next_message_with_topic(ws, "chat.response")

    assert final["text"] == f"Gelöscht: {target}"
    assert not target.exists()


def test_confirmation_denial_on_same_connection_prevents_deletion(tmp_path):
    target = tmp_path / "bleibt.txt"
    target.write_text("nicht löschen")

    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    app = create_app(config)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()

        ws.send_json({"type": "chat", "id": "x2", "text": f"/loesche {target}"})
        confirmation = _next_message_with_topic(ws, "confirmation.request")

        ws.send_json({"type": "confirmation.deny", "id": confirmation["id"]})
        final = _next_message_with_topic(ws, "chat.response")

    assert final["text"] == "Abgelehnt."
    assert target.exists()
    assert target.read_text() == "nicht löschen"
