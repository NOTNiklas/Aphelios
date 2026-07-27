"""PlanningEngine – zerlegt eine Aufgabe in ausführbare Schritte (Alpha 1.1).

Ausgelöst über den Chat mit dem Präfix ``/plan <Aufgabe>`` (server.py routet
das statt an ``chat.request`` an ``plan.request``). Nutzt Claude, um die
Aufgabe in eine kurze, geordnete Liste konkreter Schritte zu zerlegen; ohne
``ANTHROPIC_API_KEY`` greift eine einfache Heuristik (Satz-/Aufzählungsgrenzen),
damit die Engine auch im Fallback-Modus sinnvoll bleibt.

Der aktuelle Plan wird im HUD im „Aufgaben"-Panel angezeigt (echte Daten statt
Mock-Vorschau) – Schritte lassen sich dort per Checkbox als erledigt markieren
(„Ausführung" im Sinne der Roadmap; automatische Ausführung durch eine
Automation-Engine ist eine spätere Ausbaustufe, siehe ROADMAP.md Alpha 1.2).

Bus-Schnittstelle:
    * ``plan.request`` (in) – ``{id, task}``
    * ``plan.step.complete`` (in) – ``{index}`` – togglet den Schritt an ``index``
    * ``plan.update`` (out) – ``{id, task, steps: [{index, text, done}], created_at}``
    * ``chat.token`` / ``chat.response`` (out) – kurze Bestätigung im Chat
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event

PLANNING_PERSONA = """\
Du zerlegst eine Aufgabe in eine kurze, geordnete Liste konkreter, \
ausführbarer Schritte. Antworte AUSSCHLIESSLICH als nummerierte Liste \
("1. ...", "2. ...", …) auf Deutsch, ohne Einleitung, ohne Erklärung, \
maximal 6 Schritte, jeder Schritt ein kurzer, klarer Satz.
"""

_STEP_LINE_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*\S)\s*$")


def _parse_numbered_steps(text: str) -> list[str]:
    return [m.group(1) for line in text.splitlines() if (m := _STEP_LINE_RE.match(line))]


def _heuristic_steps(task: str) -> list[str]:
    """Fallback ohne AI: teilt an offensichtlichen Aufzählungs-/Satzgrenzen."""
    task = task.strip()
    if not task:
        return []
    parts = re.split(r"\s*(?:,| und | dann | danach |;)\s*", task, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [task]


async def break_into_steps(task: str, client, model: str) -> list[str]:
    """Zerlegt ``task`` in konkrete Schritte – Claude, falls verfügbar, sonst Heuristik.

    Geteilt zwischen ``PlanningEngine`` und ``ReasoningEngine`` (Werkzeug „plan"),
    damit beide dieselbe Zerlegung nutzen statt sie zweimal zu implementieren.
    """
    if client is not None:
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=400,
                system=PLANNING_PERSONA,
                messages=[{"role": "user", "content": task}],
            )
            text = "".join(block.text for block in resp.content if block.type == "text")
            steps = _parse_numbered_steps(text)
            if steps:
                return steps
        except Exception:  # noqa: BLE001 – bei jedem Claude-Fehler auf Heuristik zurückfallen
            pass
    return _heuristic_steps(task)


class PlanningEngine(BaseEngine):
    """Verwaltet genau einen aktiven Plan (Alpha 1.1: ein Nutzer, ein Fokus)."""

    name = "planning"

    async def start(self) -> None:
        self._running = True
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None
        self._plan: dict | None = None
        self.bus.subscribe("plan.request", self.handle)
        self.bus.subscribe("plan.step.complete", self._on_step_complete)

    async def handle(self, event: Event) -> None:
        task = (event.data.get("task") or "").strip()
        request_id = event.data.get("id", "") or uuid.uuid4().hex
        if not task:
            return

        steps_text = await break_into_steps(task, self._client, self.config.anthropic_model)
        self._plan = {
            "id": request_id,
            "task": task,
            "steps": [{"index": i, "text": t, "done": False} for i, t in enumerate(steps_text)],
            "created_at": time.time(),
        }
        await self.emit("plan.update", self._plan)

        reply = f"Plan erstellt: {len(steps_text)} Schritt(e) – sieh sie dir im Aufgaben-Panel an."
        for word in reply.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.03)
        await self.emit("chat.response", {"id": request_id, "text": reply, "final": True})

    async def _on_step_complete(self, event: Event) -> None:
        if not self._plan:
            return
        index = event.data.get("index")
        for step in self._plan["steps"]:
            if step["index"] == index:
                step["done"] = not step["done"]
                break
        await self.emit("plan.update", self._plan)
