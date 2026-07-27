"""Tests für Alpha 1.1: persistenter Kontext (MemoryEngine-KV), PlanningEngine
und ReasoningEngine. PlanningEngine/ReasoningEngine laufen hier bewusst ohne
``ANTHROPIC_API_KEY`` (Fallback-Pfade) – so sind sie vollständig offline und
deterministisch testbar, ohne die Anthropic-SDK-Streaming-Schnittstelle mocken
zu müssen.
"""

from __future__ import annotations

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus, request
from aphelios.core.security import SecurityGate
from aphelios.engines.conversation_engine import MAX_HISTORY_MESSAGES, ConversationEngine
from aphelios.engines.memory_engine import MemoryEngine
from aphelios.engines.planning_engine import PlanningEngine, _heuristic_steps
from aphelios.engines.reasoning_engine import ReasoningEngine, select_tool


def _memory(tmp_path) -> tuple[EventBus, Config, MemoryEngine]:
    bus = EventBus()
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    return bus, config, MemoryEngine(bus, config, SecurityGate(bus))


# -- MemoryEngine: generischer KV-Store --------------------------------------
async def test_memory_kv_roundtrip(tmp_path):
    bus, _, memory = _memory(tmp_path)
    await memory.start()

    await bus.publish(Event("memory.kv.set", {"key": "greeting", "value": {"hello": "world"}}))
    result = await request(bus, "memory.kv.get", "memory.kv.result", {"key": "greeting"})

    assert result["value"] == {"hello": "world"}
    await memory.stop()


async def test_memory_kv_get_missing_key_returns_none(tmp_path):
    bus, _, memory = _memory(tmp_path)
    await memory.start()

    result = await request(bus, "memory.kv.get", "memory.kv.result", {"key": "nope"})

    assert result["value"] is None
    await memory.stop()


async def test_memory_kv_set_overwrites_existing_value(tmp_path):
    bus, _, memory = _memory(tmp_path)
    await memory.start()

    await bus.publish(Event("memory.kv.set", {"key": "counter", "value": 1}))
    await bus.publish(Event("memory.kv.set", {"key": "counter", "value": 2}))
    result = await request(bus, "memory.kv.get", "memory.kv.result", {"key": "counter"})

    assert result["value"] == 2
    await memory.stop()


# -- ConversationEngine: persistenter Konversationskontext -------------------
async def test_conversation_history_persists_across_engine_restart(tmp_path):
    # Regression: vorher wurde jede chat.request komplett isoliert beantwortet
    # (ein Folgesatz wie "und beim RAM?" ergab keinen Sinn). Jetzt läuft der
    # Verlauf über die MemoryEngine – ein Neustart der ConversationEngine
    # (simuliert eine neue Instanz) darf ihn nicht verlieren.
    bus, config, memory = _memory(tmp_path)
    await memory.start()

    convo = ConversationEngine(bus, config, SecurityGate(bus))
    await convo.start()
    await convo._ensure_history_loaded()
    assert convo._history == []

    await convo._remember_turn("Wie spät ist es?", "Ich trage keine Uhr, Sir.")
    assert convo._history[-2:] == [
        {"role": "user", "content": "Wie spät ist es?"},
        {"role": "assistant", "content": "Ich trage keine Uhr, Sir."},
    ]

    convo_restarted = ConversationEngine(bus, config, SecurityGate(bus))
    await convo_restarted.start()
    await convo_restarted._ensure_history_loaded()
    assert convo_restarted._history == convo._history

    await memory.stop()


async def test_conversation_history_trims_to_max_length(tmp_path):
    bus, config, memory = _memory(tmp_path)
    await memory.start()
    convo = ConversationEngine(bus, config, SecurityGate(bus))
    await convo.start()
    await convo._ensure_history_loaded()

    for i in range(15):
        await convo._remember_turn(f"Frage {i}", f"Antwort {i}")

    assert len(convo._history) == MAX_HISTORY_MESSAGES
    assert convo._history[-1] == {"role": "assistant", "content": "Antwort 14"}
    await memory.stop()


async def test_conversation_memory_context_only_when_relevant(tmp_path):
    bus, config, memory = _memory(tmp_path)
    await memory.start()
    await memory.handle(
        Event("memory.note", {"title": "Docker Fehler", "content": "Fehler beim Start.", "tags": ["docker"]})
    )
    convo = ConversationEngine(bus, config, SecurityGate(bus))
    await convo.start()

    assert "Docker Fehler" in await convo._memory_context("Docker")
    assert await convo._memory_context("etwas völlig anderes xyz123") == ""
    await memory.stop()


# -- PlanningEngine ------------------------------------------------------------
def test_heuristic_steps_splits_on_conjunctions():
    assert _heuristic_steps("Küche putzen und Müll rausbringen") == [
        "Küche putzen",
        "Müll rausbringen",
    ]


def test_heuristic_steps_single_task_stays_one_step():
    assert _heuristic_steps("Präsentation vorbereiten") == ["Präsentation vorbereiten"]


async def test_planning_engine_creates_plan_without_api_key():
    bus = EventBus()
    engine = PlanningEngine(bus, Config(), SecurityGate(bus))
    await engine.start()

    updates: list[dict] = []
    bus.subscribe("plan.update", lambda e: updates.append(e.data))

    await engine.handle(Event("plan.request", {"id": "p1", "task": "Küche putzen und Müll rausbringen"}))

    assert len(updates) == 1
    plan = updates[0]
    assert plan["task"] == "Küche putzen und Müll rausbringen"
    assert [s["text"] for s in plan["steps"]] == ["Küche putzen", "Müll rausbringen"]
    assert all(step["done"] is False for step in plan["steps"])


async def test_planning_engine_toggles_step_done():
    bus = EventBus()
    engine = PlanningEngine(bus, Config(), SecurityGate(bus))
    await engine.start()
    await engine.handle(Event("plan.request", {"id": "p1", "task": "A und B"}))

    updates: list[dict] = []
    bus.subscribe("plan.update", lambda e: updates.append(e.data))

    await engine._on_step_complete(Event("plan.step.complete", {"index": 0}))
    assert updates[-1]["steps"][0]["done"] is True

    await engine._on_step_complete(Event("plan.step.complete", {"index": 0}))
    assert updates[-1]["steps"][0]["done"] is False


# -- ReasoningEngine ------------------------------------------------------------
def test_select_tool_memory_keywords():
    assert select_tool("Weißt du noch, was ich über Docker notiert hatte?") == "memory"


def test_select_tool_system_keywords():
    assert select_tool("Wie hoch ist die CPU-Auslastung gerade?") == "system"


def test_select_tool_plan_keywords():
    assert select_tool("Kannst du das in Schritte zerlegen?") == "plan"


def test_select_tool_defaults_to_direct():
    assert select_tool("Was ist die Hauptstadt von Frankreich?") == "direct"


async def test_reasoning_engine_final_response_contains_full_streamed_text():
    # Regression: chat.response muss den GESAMTEN gestreamten Text enthalten
    # (Werkzeug-Wahl + Kontext + Antwort), nicht nur die letzte Antwort-
    # Fragment – sonst ersetzt das Frontend beim Empfang von chat.response
    # (siehe hud.ts) den sichtbaren Analyse-Verlauf augenblicklich wieder
    # durch nur die finale Antwort.
    bus = EventBus()
    engine = ReasoningEngine(bus, Config(), SecurityGate(bus))
    await engine.start()

    tokens: list[str] = []
    responses: list[dict] = []
    bus.subscribe("chat.token", lambda e: tokens.append(e.data["text"]))
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle(Event("reasoning.request", {"id": "r1", "text": "Was ist die Hauptstadt von Frankreich?"}))

    assert len(responses) == 1
    full_streamed = "".join(tokens)
    assert responses[0]["text"] == full_streamed
    assert "Werkzeug gewählt: **direct**" in full_streamed


async def test_reasoning_engine_system_tool_uses_cached_stats():
    bus = EventBus()
    engine = ReasoningEngine(bus, Config(), SecurityGate(bus))
    await engine.start()
    await bus.publish(
        Event("system.stats", {"cpu": {"percent": 42.0}, "ram": {"percent": 55.0}, "temperature": None})
    )

    tokens: list[str] = []
    bus.subscribe("chat.token", lambda e: tokens.append(e.data["text"]))

    await engine.handle(Event("reasoning.request", {"id": "r2", "text": "Wie ist die CPU-Auslastung?"}))

    assert "CPU 42.0%, RAM 55.0%" in "".join(tokens)


async def test_reasoning_engine_memory_tool_reports_no_hits(tmp_path):
    bus, config, memory = _memory(tmp_path)
    await memory.start()
    engine = ReasoningEngine(bus, config, SecurityGate(bus))
    await engine.start()

    tokens: list[str] = []
    bus.subscribe("chat.token", lambda e: tokens.append(e.data["text"]))

    await engine.handle(Event("reasoning.request", {"id": "r3", "text": "Weißt du noch was über Raketentriebwerke?"}))

    assert "Keine passenden Notizen im Vault gefunden" in "".join(tokens)
    await memory.stop()
