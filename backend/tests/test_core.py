"""Tests für den APHELIOS-Kern: Event-Bus, Engine-Lebenszyklus, Security, Memory."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from aphelios.core.config import BACKEND_ROOT, Config, _get, _resolve_path
from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event, EventBus, request
from aphelios.core.manager import EngineManager
from aphelios.core.security import RiskLevel, SecurityGate
from aphelios.engines.memory_engine import MemoryEngine, _age_phrase, _search_tokens
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


def test_resolve_path_keeps_absolute_paths_unchanged():
    # Plattformunabhängig testen: ein echter absoluter Pfad dieses Systems.
    absolute = str(Path(__file__).resolve())
    assert _resolve_path(absolute) == Path(absolute)


def test_resolve_path_anchors_relative_paths_to_backend_root():
    # Regression: relative Pfade (z. B. der Default "./data/google_token.json")
    # wurden bisher gegen das aktuelle Arbeitsverzeichnis aufgelöst – je
    # nachdem, wie/von wo das Backend gestartet wurde (Terminal mit `cd
    # backend`, run.bat, IDE-Run-Konfiguration, …), zeigte derselbe relative
    # Pfad auf unterschiedliche Orte. Ein einmal per scripts/google_auth.py
    # erzeugtes Token wurde dadurch je nach Startart nicht mehr gefunden,
    # obwohl an der Anmeldung selbst nichts falsch war.
    assert _resolve_path("./data/google_token.json") == BACKEND_ROOT / "data/google_token.json"


def test_resolve_path_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _resolve_path("./vault") == BACKEND_ROOT / "vault"


def test_from_env_anchors_default_paths_to_backend_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = Config.from_env()
    assert config.vault_path == BACKEND_ROOT / "vault"
    assert config.db_path == BACKEND_ROOT / "data" / "aphelios.sqlite"
    assert config.google_token_path == BACKEND_ROOT / "data" / "google_token.json"


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


# -- MemoryEngine: Vektorsuche (Alpha 1.5) -----------------------------------
class _FakeChromaCollection:
    """Steht für eine echte ChromaDB-Kollektion ein – injiziert per
    ``engine._chroma_collection`` (derselbe Trick wie ``engine._piper_voice``
    in test_voice.py), damit Tests deterministisch bleiben und kein echtes
    Embedding-Modell brauchen."""

    def __init__(self, query_result: dict | None = None) -> None:
        self.upserts: list[dict] = []
        self._query_result = query_result or {"ids": [[]], "metadatas": [[]], "distances": [[]]}

    def upsert(self, ids, documents, metadatas) -> None:  # noqa: ANN001
        self.upserts.append({"ids": ids, "documents": documents, "metadatas": metadatas})

    def query(self, query_texts, n_results):  # noqa: ANN001
        return self._query_result


async def test_memory_search_falls_back_to_fulltext_when_chroma_unavailable(tmp_path):
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()
    engine._chroma_init_error = "simuliert: chromadb nicht installiert"  # erzwingt Fallback

    await engine.handle(
        Event("memory.note", {"title": "Docker Fehler", "content": "Fehler beim Start.", "tags": ["docker"]})
    )
    result = await request(bus, "memory.search", "memory.result", {"query": "Docker"})

    assert result["results"][0]["title"] == "Docker Fehler"
    assert result["results"][0]["age"] == "heute"
    await engine.stop()


async def test_memory_note_upserts_into_chroma_when_available(tmp_path):
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()
    fake = _FakeChromaCollection()
    engine._chroma_collection = fake  # _ensure_chroma() gibt das jetzt direkt zurück

    await engine.handle(Event("memory.note", {"title": "Testnotiz", "content": "Inhalt hier"}))

    assert len(fake.upserts) == 1
    assert fake.upserts[0]["metadatas"][0]["title"] == "Testnotiz"
    await engine.stop()


async def test_memory_note_save_succeeds_even_if_chroma_upsert_fails(tmp_path):
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()

    class _BrokenCollection(_FakeChromaCollection):
        def upsert(self, ids, documents, metadatas):  # noqa: ANN001
            raise RuntimeError("Vektor-Index kaputt")

    engine._chroma_collection = _BrokenCollection()

    await engine.handle(Event("memory.note", {"title": "Trotzdem gespeichert", "content": "x"}))

    assert (config.vault_path / "Notizen" / "Trotzdem-gespeichert.md").exists()
    await engine.stop()


async def test_memory_search_uses_semantic_hits_and_filters_low_relevance(tmp_path):
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()
    now = time.time()
    engine._chroma_collection = _FakeChromaCollection(
        {
            "ids": [["vault/wissen/relevant.md", "vault/notizen/irrelevant.md"]],
            "metadatas": [
                [
                    {"title": "Relevant", "category": "Wissen", "created_at": now},
                    {"title": "Irrelevant", "category": "Notizen", "created_at": now},
                ]
            ],
            # Unter der _MAX_SEMANTIC_DISTANCE-Schwelle bleibt, drüber fliegt raus –
            # sonst würde bei nur einer Notiz im Vault JEDE Anfrage "Treffer" liefern.
            "distances": [[0.5, 1.6]],
        }
    )

    result = await request(bus, "memory.search", "memory.result", {"query": "irgendwas"})

    assert [r["title"] for r in result["results"]] == ["Relevant"]
    await engine.stop()


async def test_memory_search_falls_back_to_fulltext_when_semantic_hits_all_filtered_out(tmp_path):
    # Regression, live über Playwright gefunden: "/plan Kuchen backen und
    # Kueche putzen" legt eine Notiz an, "/wissen Was war nochmal mein
    # Plan?" fand sie danach NICHT – die Vektorsuche lief (ChromaDB
    # verfügbar), lieferte aber nur Treffer über der Distanz-Schwelle
    # zurück (leere Liste statt None). Der alte Code fiel nur bei
    # "Vektorsuche komplett nicht verfügbar" (None) auf Volltext zurück,
    # nicht bei "lief, aber nichts Relevantes gefunden" ([]).
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()
    engine._chroma_collection = _FakeChromaCollection()  # start(): leere Query-Ergebnisse

    await engine.handle(
        Event(
            "memory.note",
            {
                "title": "Kuchen backen und Kueche putzen",
                "content": "Status: 0/2 Schritte erledigt\n\n- [ ] Kuchen backen\n- [ ] Kueche putzen",
                "category": "Projekte",
                "tags": ["plan", "projekt"],
            },
        )
    )
    # Simuliert: Vektorsuche lief, aber der einzige "Nachbar" liegt über der
    # Relevanz-Schwelle (die Frage teilt semantisch kaum Wörter mit der
    # Notiz) – die Fake-Query gibt absichtlich einen zu hohen Distanzwert
    # zurück, unabhängig von der Anfrage.
    engine._chroma_collection._query_result = {
        "ids": [["irrelevant-id"]],
        "metadatas": [[{"title": "Kuchen backen und Kueche putzen", "category": "Projekte", "created_at": time.time()}]],
        "distances": [[1.65]],
    }

    result = await request(bus, "memory.search", "memory.result", {"query": "Was war nochmal mein Plan?"})

    assert [r["title"] for r in result["results"]] == ["Kuchen backen und Kueche putzen"]
    await engine.stop()


async def test_fulltext_search_matches_single_keyword_not_whole_phrase(tmp_path):
    # Der alte Code verlangte die GANZE Anfrage als einen Substring – bei
    # einer natürlichen Frage praktisch nie ein Treffer. Jetzt reicht ein
    # bedeutungstragendes Wort daraus.
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()
    engine._chroma_init_error = "simuliert: keine Vektorsuche in diesem Test"

    await engine.handle(
        Event("memory.note", {"title": "Docker Compose Notizen", "content": "Mehrere Container starten."})
    )

    result = await request(bus, "memory.search", "memory.result", {"query": "Wie starte ich meinen Docker Container nochmal?"})

    assert [r["title"] for r in result["results"]] == ["Docker Compose Notizen"]
    await engine.stop()


async def test_fulltext_search_matches_tags(tmp_path):
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    engine = MemoryEngine(bus, config, SecurityGate(bus))
    await engine.start()
    engine._chroma_init_error = "simuliert: keine Vektorsuche in diesem Test"

    await engine.handle(
        Event(
            "memory.note",
            {"title": "Kuchen backen und Kueche putzen", "content": "- [ ] Kuchen backen", "tags": ["plan"]},
        )
    )

    result = await request(bus, "memory.search", "memory.result", {"query": "Was war nochmal mein Plan?"})

    assert [r["title"] for r in result["results"]] == ["Kuchen backen und Kueche putzen"]
    await engine.stop()


def test_search_tokens_drops_stopwords_and_keeps_keywords():
    assert _search_tokens("Was war nochmal mein Plan?") == ["plan"]
    assert _search_tokens("Wie starte ich meinen Docker Container nochmal?") == [
        "starte",
        "docker",
        "container",
    ]
    # Nur Stoppwörter/zu kurze Wörter -> leer, kein Absturz.
    assert _search_tokens("Was ist das?") == []


def test_age_phrase_buckets():
    now = time.time()
    assert _age_phrase(now) == "heute"
    assert _age_phrase(now - 1.5 * 86400) == "gestern"
    assert _age_phrase(now - 3 * 86400) == "vor 3 Tagen"
    assert _age_phrase(now - 21 * 86400) == "vor 3 Wochen"
    assert _age_phrase(now - 90 * 86400) == "vor 3 Monaten"
    assert _age_phrase(now - 400 * 86400) == "vor 1 Jahr"
    assert _age_phrase(now - 800 * 86400) == "vor 2 Jahren"


# -- WeatherEngine -------------------------------------------------------
def test_describe_weather_code_known_and_unknown():
    assert describe_weather_code(0) == "Klarer Himmel"
    assert describe_weather_code(95) == "Gewitter"
    assert describe_weather_code(9999) == "Unbekannt"
    assert describe_weather_code(None) == "Unbekannt"
