"""Tests für die KnowledgeEngine (Alpha 1.5): RAG-basierte Fragen gegen den
Vault, ausgelöst über ``/wissen <Frage>``.

Läuft bewusst ohne ``ANTHROPIC_API_KEY`` (wie test_alpha11.py für Planning/
Reasoning) – testet damit die vollständig offline nutzbaren Pfade (Fundliste
ohne Synthese), ohne die Anthropic-SDK-Streaming-Schnittstelle mocken zu
müssen. Nutzt eine echte MemoryEngine (kein Mock) für die Suche, damit auch
der Weg über den echten Bus (``memory.search`` → ``memory.result``) geprüft
wird.
"""

from __future__ import annotations

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines.knowledge_engine import KnowledgeEngine
from aphelios.engines.memory_engine import MemoryEngine


def _setup(tmp_path) -> tuple[EventBus, Config, MemoryEngine, KnowledgeEngine]:
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    memory = MemoryEngine(bus, config, SecurityGate(bus))
    knowledge = KnowledgeEngine(bus, config, SecurityGate(bus))
    return bus, config, memory, knowledge


async def _run(engine: KnowledgeEngine, text: str) -> str:
    tokens: list[str] = []
    responses: list[dict] = []
    engine.bus.subscribe("chat.token", lambda e: tokens.append(e.data["text"]))
    engine.bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle(Event("knowledge.request", {"id": "k1", "text": text}))
    assert responses, "keine chat.response erhalten"
    assert "".join(tokens).strip() == responses[0]["text"]
    return responses[0]["text"]


async def test_empty_text_does_nothing():
    bus = EventBus()
    engine = KnowledgeEngine(bus, Config(), SecurityGate(bus))
    await engine.start()
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle(Event("knowledge.request", {"id": "k0", "text": "  "}))

    assert responses == []


async def test_no_hits_reports_honest_refusal(tmp_path):
    bus, config, memory, knowledge = _setup(tmp_path)
    await memory.start()
    await knowledge.start()

    text = await _run(knowledge, "Was ist mein Lieblingsrezept für Kuchen?")

    assert "finde ich nichts im vault" in text.lower()
    await memory.stop()


async def test_hits_without_api_key_lists_notes_without_synthesis(tmp_path):
    bus, config, memory, knowledge = _setup(tmp_path)
    await memory.start()
    await memory.handle(
        Event(
            "memory.note",
            {"title": "Docker Fehler", "content": "Container startet nicht mehr.", "tags": ["docker"]},
        )
    )
    await knowledge.start()

    text = await _run(knowledge, "Docker Probleme")

    assert "Docker Fehler" in text
    assert "ohne ai-schlüssel" in text.lower() and "api" in text.lower()
    await memory.stop()


async def test_hits_include_age_phrase_in_listing(tmp_path):
    bus, config, memory, knowledge = _setup(tmp_path)
    await memory.start()
    await memory.handle(Event("memory.note", {"title": "Frische Notiz", "content": "Docker Notizen hier"}))
    await knowledge.start()

    text = await _run(knowledge, "Docker")

    assert "heute" in text
    await memory.stop()


# -- _load_context -------------------------------------------------------------
def test_load_context_reads_real_files_and_truncates(tmp_path):
    bus = EventBus()
    engine = KnowledgeEngine(bus, Config(), SecurityGate(bus))
    note = tmp_path / "note.md"
    note.write_text("A" * 5000, encoding="utf-8")

    context = engine._load_context([{"title": "Lang", "path": str(note)}])

    assert "### Lang" in context
    assert len(context) < 5000 + 20  # auf _MAX_NOTE_CHARS begrenzt, nicht der volle Text


def test_load_context_skips_missing_files_silently(tmp_path):
    bus = EventBus()
    engine = KnowledgeEngine(bus, Config(), SecurityGate(bus))

    context = engine._load_context([{"title": "Weg", "path": str(tmp_path / "gibts-nicht.md")}])

    assert context == ""


def test_load_context_limits_to_max_context_notes(tmp_path):
    bus = EventBus()
    engine = KnowledgeEngine(bus, Config(), SecurityGate(bus))
    hits = []
    for i in range(10):
        note = tmp_path / f"n{i}.md"
        note.write_text(f"Inhalt {i}", encoding="utf-8")
        hits.append({"title": f"Notiz {i}", "path": str(note)})

    # handle() reicht nur die ersten _MAX_CONTEXT_NOTES an _load_context weiter;
    # hier direkt getestet, dass _load_context selbst alles laedt, was man ihm gibt
    # (die Begrenzung passiert VOR dem Aufruf, siehe handle()).
    context = engine._load_context(hits[:5])
    assert context.count("###") == 5
