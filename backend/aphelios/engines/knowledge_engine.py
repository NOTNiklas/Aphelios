"""KnowledgeEngine – RAG-basierte Fragen direkt gegen den Obsidian-Vault
(Alpha 1.5, erste Ausbaustufe).

Ausgelöst über den Chat mit dem Präfix ``/wissen <Frage>``. Unterscheidet sich
bewusst von den beiden bestehenden Vault-Nutzern:

    * ``ConversationEngine`` reicht Vault-Treffer nur als **kurzen
      Kontext-Hinweis** in den System-Prompt – der Vault ist Hintergrundwissen,
      keine gezielte Anfrage.
    * ``ReasoningEngine`` wählt den Vault nur als **eine von mehreren**
      möglichen Quellen (neben System-Werten, Aufgaben-Zerlegung, …).
    * ``KnowledgeEngine`` durchsucht **immer** semantisch den Vault, zeigt die
      gefundenen Notizen sichtbar (Titel + Alter, "vor 3 Monaten" – siehe
      ``MemoryEngine``), lädt ihre Volltexte von der Platte und lässt Claude
      **ausschließlich** auf dieser Basis antworten – klassisches RAG
      (Retrieval-Augmented Generation) mit Quellenangabe.

Ohne Treffer: ehrliche Rückmeldung statt einer erfundenen Antwort. Ohne
``ANTHROPIC_API_KEY``: nur die gefundenen Notizen auflisten, keine Synthese –
dasselbe Fallback-Prinzip wie bei Planning-/ReasoningEngine.

Bus-Schnittstelle:
    * ``knowledge.request`` (in) – ``{id, text}``
    * ``memory.search`` (out) / ``memory.result`` (in) – über
      ``aphelios.core.event_bus.request`` (Anfrage/Antwort-Muster)
    * ``chat.token`` / ``chat.response`` (out) – wie ReasoningEngine
"""

from __future__ import annotations

from pathlib import Path

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event, request

KNOWLEDGE_PERSONA = """\
Du bist APHELIOS im Wissens-Modus. Beantworte die Frage AUSSCHLIESSLICH auf \
Basis der unten angehängten Notizen aus dem Obsidian-Vault des Nutzers – \
erfinde nichts hinzu, was dort nicht steht. Nenne kurz, welche Notiz(en) du \
für deine Antwort verwendet hast. Steht die Antwort nicht in den Notizen, \
sag das ehrlich statt zu spekulieren. Ruhig, präzise, auf Deutsch.
"""

#: Wie viele Top-Treffer als Volltext in den Claude-Kontext einfließen.
_MAX_CONTEXT_NOTES = 5
#: Zeichen-Obergrenze je Notiz im Kontext (Tokens/Kosten begrenzen).
_MAX_NOTE_CHARS = 2000


class KnowledgeEngine(BaseEngine):
    """Beantwortet Fragen ausschließlich auf Basis semantisch gefundener
    Vault-Notizen (RAG) – mit sichtbarer Quellenangabe."""

    name = "knowledge"

    async def start(self) -> None:
        self._running = True
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None
        self.bus.subscribe("knowledge.request", self.handle)

    async def handle(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")
        if not text:
            return

        buffer: list[str] = []

        async def say(chunk: str) -> None:
            buffer.append(chunk)
            await self.emit("chat.token", {"id": request_id, "text": chunk})

        result = await request(self.bus, "memory.search", "memory.result", {"query": text}, timeout=3.0)
        hits = (result or {}).get("results") or []

        if not hits:
            await say("Dazu finde ich nichts im Vault – frag mich etwas anderes oder merke es dir erst per Notiz.")
            await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})
            return

        top_hits = hits[:_MAX_CONTEXT_NOTES]
        listing = ", ".join(f'„{h["title"]}" ({h.get("age", "?")})' for h in top_hits)
        await say(f"_Gefunden im Vault: {listing}._\n\n")

        if self._client is None:
            await say(
                "_Ohne AI-Schlüssel bleibt es bei der Fundliste oben – trage einen "
                "ANTHROPIC_API_KEY in die .env ein für eine echte Antwort._"
            )
            await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})
            return

        context = self._load_context(top_hits)
        if not context:
            await say(
                "_Die gefundenen Notizen ließen sich nicht von der Platte lesen "
                "(verschoben/gelöscht?) – keine Antwort möglich._"
            )
            await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})
            return

        system = KNOWLEDGE_PERSONA + f"\n\nNotizen aus dem Vault:\n\n{context}"
        try:
            async with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=800,
                system=system,
                messages=[{"role": "user", "content": text}],
            ) as stream:
                async for chunk in stream.text_stream:
                    await say(chunk)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Wissens-Anfrage an Claude fehlgeschlagen")
            await say(f"\n\nAntwort fehlgeschlagen: {str(exc)[:200]}")

        await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})

    # -- intern ---------------------------------------------------------------
    def _load_context(self, hits: list[dict]) -> str:
        """Lädt die Volltexte der Treffer von der Platte für den RAG-Kontext.

        Der Suchindex (``memory.search``) liefert bewusst nur Metadaten
        (Titel/Kategorie/Pfad/Alter), keine vollen Inhalte – die liegen
        bereits als Markdown-Dateien im Vault, ein zweiter RPC-Umweg wäre
        unnötig.
        """
        blocks: list[str] = []
        for hit in hits:
            path = hit.get("path")
            if not path:
                continue
            try:
                text = Path(path).read_text(encoding="utf-8")
            except OSError:
                continue
            blocks.append(f"### {hit.get('title', path)}\n{text[:_MAX_NOTE_CHARS]}")
        return "\n\n".join(blocks)
