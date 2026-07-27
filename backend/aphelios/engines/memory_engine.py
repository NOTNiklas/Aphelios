"""MemoryEngine – Obsidian-Vault als Langzeitgedächtnis (Second Brain).

Persistiert Informationen als Markdown-Notizen in einem Obsidian-Vault:
YAML-Frontmatter mit ``tags``, automatische Einsortierung in Kategorien
(Personen, Projekte, Ideen, Code, Fehler, Lösungen …) und ``[[Backlinks]]``.
Ein SQLite-Index ermöglicht schnelles Wiederfinden.

**Automatische Verknüpfung (Graph View):** Jede neue Notiz wird automatisch mit
thematisch verwandten Notizen verlinkt – verwandt heißt: gleiche Kategorie oder
mindestens ein gemeinsamer Tag. Diese ``[[Wikilinks]]`` reichen aus, damit
Obsidians eingebauter **Graph View** und das **Backlinks-Panel** die
Datenpakete automatisch als verbundenes Netz darstellen – dafür ist keine
zusätzliche Konfiguration in Obsidian nötig, nur der richtige Vault-Pfad
(``APHELIOS_VAULT_PATH`` in der ``.env``, siehe ``.env.example``).

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
        tags = list(event.data.get("tags") or [])
        explicit_links = list(event.data.get("links") or [])

        # Automatische Verknüpfung: verwandte Notizen (gleiche Kategorie oder
        # gemeinsame Tags) werden zusätzlich zu expliziten Links verlinkt –
        # das Ergebnis sieht Obsidians Graph View als verbundenes Netz.
        related = self._find_related(tags, category, exclude_title=title)
        links = list(dict.fromkeys(explicit_links + related))  # Duplikate raus, Reihenfolge bleibt

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

    def _find_related(
        self, tags: list[str], category: str, exclude_title: str, limit: int = 6
    ) -> list[str]:
        """Findet thematisch verwandte Notizen für automatische Backlinks.

        „Verwandt" = mindestens ein gemeinsamer Tag ODER dieselbe Kategorie.
        Ergebnis nach Anzahl gemeinsamer Merkmale sortiert (mehr Überlappung
        zuerst), damit die engsten Verwandten oben stehen.
        """
        own_tags = {t.strip().lower() for t in tags if t.strip()} | {category.lower()}
        if not own_tags:
            return []

        rows = self._db.execute(
            "SELECT title, category, tags FROM notes "
            "WHERE title != ? ORDER BY created_at DESC LIMIT 300",
            (exclude_title,),
        ).fetchall()

        scored: list[tuple[int, str]] = []
        for other_title, other_category, other_tags in rows:
            other_set = {
                t.strip().lower() for t in (other_tags or "").split(",") if t.strip()
            } | {(other_category or "").lower()}
            overlap = len(own_tags & other_set)
            if overlap > 0:
                scored.append((overlap, other_title))

        scored.sort(key=lambda pair: -pair[0])
        # Bei Titel-Duplikaten (Notiz wurde aktualisiert) nur einmal zählen.
        seen: set[str] = set()
        result: list[str] = []
        for _, other_title in scored:
            if other_title in seen:
                continue
            seen.add(other_title)
            result.append(other_title)
            if len(result) >= limit:
                break
        return result

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

        # Kategorie zusätzlich als Tag aufnehmen (dedupliziert) – das lässt
        # Obsidians Tag-Panel und den Graph automatisch nach Kategorie clustern.
        all_tags = list(dict.fromkeys([*tags, category.lower()]))

        now = datetime.now(timezone.utc).isoformat()
        frontmatter = [
            "---",
            f"title: {title}",
            f"category: {category}",
            f"created: {now}",
            "tags:",
            *[f"  - {tag}" for tag in all_tags],
            "---",
            "",
        ]
        body = [f"# {title}", "", content, ""]
        if links:
            body += ["## Verknüpfungen", "", *[f"- [[{link}]]" for link in links], ""]

        path.write_text("\n".join(frontmatter + body), encoding="utf-8")
        return path
