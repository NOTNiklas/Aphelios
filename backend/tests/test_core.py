"""Tests für den APHELIOS-Kern: Event-Bus, Engine-Lebenszyklus, Security, Memory."""

from __future__ import annotations

import asyncio

import pytest

from aphelios.core.config import Config, _get
from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.manager import EngineManager
from aphelios.core.security import RiskLevel, SecurityGate
from aphelios.engines.memory_engine import MemoryEngine
from aphelios.engines.weather_engine import describe_weather_code


# -- Config --------------------------------------------------------------
def test_get_strips_whitespace_and_quotes(monkeypatch):
    # Regression: "KEY= wert" (Leerzeichen nach dem "=") machte z. B. einen
    # API-Key unbemerkt ungültig – die Anfrage schlug fehl, ohne dass der
    # Nutzer den Grund sah (siehe ConversationEngine-Fallback).
    monkeypatch.setenv("APHELIOS_TEST_KEY", " sk-ant-abc123 ")
    assert _get("APHELIOS_TEST_KEY", "") == "sk-ant-abc123"

    monkeypatch.setenv("APHELIOS_TEST_KEY", '"sk-ant-xyz"')
    assert _get("APHELIOS_TEST_KEY", "") == "sk-ant-xyz"


def test_config_has_anthropic_respects_stripped_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    # Nur Leerzeichen → nach dem Trimmen leer → gilt als "kein Key".
    assert Config.from_env().has_anthropic is False


# -- Event-Bus ---------------------------------------------------------------
async def test_eventbus_exact_delivery():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("chat.request", lambda e: received.append(e))
    await bus.publish(Event("chat.request", {"text": "hi"}))
    await bus.publish(Event("system.stats", {"cpu": 1}))  # darf nicht ankommen
    assert len(received) == 1
    assert received[0].data["text"] == "hi"


async def test_eventbus_wildcard():
    bus = EventBus()
    received: list[str] = []
    bus.subscribe("system.*", lambda e: received.append(e.topic))
    bus.subscribe("*", lambda e: received.append("ALL:" + e.topic))
    await bus.publish(Event("system.stats"))
    assert "system.stats" in received
    assert "ALL:system.stats" in received


async def test_eventbus_async_handler():
    bus = EventBus()
    hits: list[int] = []

    async def handler(_: Event) -> None:
        await asyncio.sleep(0)
        hits.append(1)

    bus.subscribe("x.y", handler)
    await bus.publish(Event("x.y"))
    assert hits == [1]


# -- Engine-Lebenszyklus -----------------------------------------------------
class _DummyEngine(BaseEngine):
    name = "dummy"

    async def start(self) -> None:
        self._running = True


async def test_engine_manager_lifecycle():
    bus = EventBus()
    config = Config()
    security = SecurityGate(bus)
    manager = EngineManager()
    engine = _DummyEngine(bus, config, security)
    manager.register(engine)

    await manager.start_all()
    assert manager.status()["dummy"] == "online"

    await manager.stop_all()
    assert manager.status()["dummy"] == "offline"


async def test_engine_manager_rejects_duplicate():
    manager = EngineManager()
    bus, config, security = EventBus(), Config(), SecurityGate(EventBus())
    manager.register(_DummyEngine(bus, config, security))
    with pytest.raises(ValueError):
        manager.register(_DummyEngine(bus, config, security))


# -- Security ----------------------------------------------------------------
async def test_security_safe_is_immediate():
    gate = SecurityGate(EventBus())
    assert await gate.request("read", level=RiskLevel.SAFE) is True


async def test_security_denies_without_approval():
    gate = SecurityGate(EventBus(), default_timeout=0.05)
    allowed = await gate.request("delete_file", level=RiskLevel.CONFIRM)
    assert allowed is False  # deny by default


async def test_security_approves_on_event():
    bus = EventBus()
    gate = SecurityGate(bus, default_timeout=2.0)

    captured: dict[str, str] = {}

    async def approve(event: Event) -> None:
        captured["id"] = event.data["id"]
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve)
    allowed = await gate.request("delete_file", level=RiskLevel.CONFIRM)
    assert allowed is True
    assert "id" in captured


# -- MemoryEngine ------------------------------------------------------------
async def test_memory_engine_writes_vault(tmp_path):
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()

    await engine.handle(
        Event(
            "memory.note",
            {
                "title": "Docker Fehler",
                "content": "Es gab einen error beim Start des Containers.",
                "tags": ["docker", "infra"],
                "links": ["Projekt X"],
            },
        )
    )
    await engine.stop()

    # Automatische Kategorisierung → "Fehler" (Schlüsselwort "error"/"fehler").
    note = (config.vault_path / "Fehler" / "Docker-Fehler.md").read_text(encoding="utf-8")
    assert "title: Docker Fehler" in note
    assert "- docker" in note
    assert "[[Projekt X]]" in note
    # Kategorie landet zusätzlich als Tag im Frontmatter (Graph-Clustering).
    assert "- fehler" in note


async def test_memory_engine_auto_links_related_notes(tmp_path):
    # Regression/Feature: Notizen mit gemeinsamem Tag oder gleicher Kategorie
    # sollen automatisch per [[Wikilink]] verbunden werden, damit Obsidians
    # Graph View die Verbindungen zeigt – ganz ohne manuelles Verlinken.
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()

    await engine.handle(
        Event(
            "memory.note",
            {"title": "Docker Setup Notizen", "content": "Grundkonfiguration.", "tags": ["docker"]},
        )
    )
    await engine.handle(
        Event(
            "memory.note",
            {"title": "Docker Compose Notizen", "content": "Mehrere Container.", "tags": ["docker"]},
        )
    )
    await engine.stop()

    note = (
        config.vault_path / "Notizen" / "Docker-Compose-Notizen.md"
    ).read_text(encoding="utf-8")
    assert "[[Docker Setup Notizen]]" in note


# -- WeatherEngine -------------------------------------------------------
def test_describe_weather_code_known_and_unknown():
    assert describe_weather_code(0) == "Klarer Himmel"
    assert describe_weather_code(95) == "Gewitter"
    assert describe_weather_code(9999) == "Unbekannt"
    assert describe_weather_code(None) == "Unbekannt"
