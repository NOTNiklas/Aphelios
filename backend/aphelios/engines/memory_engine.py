"""MemoryEngine – Obsidian-Vault als Langzeitgedächtnis (Second Brain).

Persistiert Informationen als Markdown-Notizen in einem Obsidian-Vault:
YAML-Frontmatter mit ``tags``, automatische Einsortierung in Kategorien
(Personen, Projekte, Ideen, Code, Fehler, Lösungen …) und ``[[Backlinks]]``.
Ein SQLite-Index ermöglicht schnelles Wiederfinden.

Bus-Schnittstelle:
    * ``memory.note`` (in)  – ``{title, content, category?, tags?, links?}`` speichern
    * ``memory.search`` (in) – ``{id, query}`` → antwortet mit ``memory.result``

Vektorsuche (ChromaDB) ist als spätere Ausbaustufe vorgesehen (siehe Roadmap).
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event

#: Vom Spec vorgegebene Kategorien (= Vault-Unterordner).
CATEGORIES = [
    "Personen",
    "Projekte",
    "Ideen",
    "Code",
    "Dokumentationen",
    "Meetings",
    "Lernmaterial",
    "Fehler",
    "Lösungen",
    "Wissen",
    "Notizen",
    "Aufgaben",
    "Protokolle",
]

_SLUG_RE = re.compile(r"[^\w\-]+", re.UNICODE)


def _slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.strip()).strip("-")
    return slug or "notiz"


class MemoryEngine(BaseEngine):
    """Schreibt und findet Markdown-Notizen im Obsidian-Vault."""

    name = "memory"

    async def start(self) -> None:
        self._running = True
        self.vault = self.config.vault_path
        self.vault.mkdir(parents=True, exist_ok=True)
        for category in CATEGORIES:
            (self.vault / category).mkdir(exist_ok=True)

        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.config.db_path)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                tags TEXT,
                path TEXT NOT NULL,
                content TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        self._db.commit()

        self.bus.subscribe("memory.note", self.handle)
        self.bus.subscribe("memory.search", self._on_search)
        self.log.info("Vault bereit unter %s", self.vault.resolve())

    async def stop(self) -> None:
        self._running = False
        db = getattr(self, "_db", None)
        if db:
            db.close()

    async def handle(self, event: Event) -> None:
        """Speichert eine Notiz (``memory.note``)."""
        title = (event.data.get("title") or "").strip()
        content = event.data.get("content") or ""
        if not title:
            return
        category = event.data.get("category") or self._classify(f"{title}\n{content}")
        tags = event.data.get("tags") or []
        links = event.data.get("links") or []
        path = self._write_note(title, content, category, tags, links)

        self._db.execute(
            "INSERT INTO notes (title, category, tags, path, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, category, ",".join(tags), str(path), content, time.time()),
        )
        self._db.commit()
        await self.emit("memory.saved", {"title": title, "category": category, "path": str(path)})

    async def _on_search(self, event: Event) -> None:
        """Einfache Volltextsuche über den SQLite-Index (``memory.search``)."""
        query = (event.data.get("query") or "").strip()
        request_id = event.data.get("id", "")
        rows = self._db.execute(
            "SELECT title, category, path FROM notes "
            "WHERE title LIKE ? OR content LIKE ? ORDER BY created_at DESC LIMIT 10",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
        results = [{"title": r[0], "category": r[1], "path": r[2]} for r in rows]
        await self.emit("memory.result", {"id": request_id, "query": query, "results": results})

    # -- intern ---------------------------------------------------------------
    def _classify(self, text: str) -> str:
        """Heuristische Kategorisierung anhand von Schlüsselwörtern."""
        lowered = text.lower()
        rules = {
            "Fehler": ("fehler", "error", "exception", "traceback", "bug"),
            "Lösungen": ("lösung", "gelöst", "fix", "workaround"),
            "Code": ("def ", "function", "import ", "class ", "```"),
            "Projekte": ("projekt", "repository", "repo"),
            "Meetings": ("meeting", "besprechung", "termin"),
            "Aufgaben": ("todo", "aufgabe", "task"),
            "Personen": ("person", "kontakt", "kollege"),
        }
        for category, keywords in rules.items():
            if any(keyword in lowered for keyword in keywords):
                return category
        return "Notizen"

    def _write_note(
        self,
        title: str,
        content: str,
        category: str,
        tags: list[str],
        links: list[str],
    ) -> Path:
        folder = self.vault / (category if category in CATEGORIES else "Notizen")
        folder.mkdir(exist_ok=True)
        path = folder / f"{_slugify(title)}.md"

        now = datetime.now(timezone.utc).isoformat()
        frontmatter = [
            "---",
            f"title: {title}",
            f"category: {category}",
            f"created: {now}",
            "tags:",
            *[f"  - {tag}" for tag in tags],
            "---",
            "",
        ]
        body = [f"# {title}", "", content, ""]
        if links:
            body += ["## Verknüpfungen", "", *[f"- [[{link}]]" for link in links], ""]

        path.write_text("\n".join(frontmatter + body), encoding="utf-8")
        return path
