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

**Update statt Duplikat:** Titel + Kategorie bestimmen den Dateipfad – ein
zweites ``memory.note`` mit demselben Titel/derselben Kategorie überschreibt
also dieselbe Datei (statt eine zweite anzulegen) und ersetzt auch den
zugehörigen SQLite-Eintrag. ``created`` bleibt dabei stabil, ein zusätzliches
``updated`` markiert die letzte Änderung. Darauf bauen Engines auf, die
denselben Vorgang wiederholt protokollieren – z. B. die ``PlanningEngine``,
die ihre „Projekte"-Notiz bei jedem abgehakten Schritt aktualisiert, statt
für jeden Schritt eine neue Notiz zu erzeugen.

Bus-Schnittstelle:
    * ``memory.note`` (in)  – ``{title, content, category?, tags?, links?}``
      speichern/aktualisieren
    * ``memory.search`` (in) – ``{id, query}`` → antwortet mit ``memory.result``
    * ``memory.kv.set`` (in) – ``{key, value}`` – generischer, persistenter
      Key-Value-Speicher für andere Engines (JSON-serialisierbarer ``value``).
      Gedacht für internen Zustand, der einen Neustart überleben soll, aber
      keine eigene Obsidian-Notiz braucht (z. B. der Konversationsverlauf der
      ``ConversationEngine`` – siehe Alpha 1.1, ``docs/engines.md``).
    * ``memory.kv.get`` (in) – ``{id, key}`` → antwortet mit ``memory.kv.result``
      ``{id, key, value}`` (``value: null`` falls nicht vorhanden)

**Vektorsuche (Alpha 1.5, optional):** ``memory.search`` versucht zuerst eine
semantische Suche über [ChromaDB](https://www.trychroma.com/) (lokale
Embeddings, standardmäßig `all-MiniLM-L6-v2`, kein API-Key nötig – das Modell
wird beim ersten Gebrauch automatisch heruntergeladen und lokal
zwischengespeichert). Ist ChromaDB nicht installiert (`pip install -e
".[vector]"`) oder schlägt der einmalige Modell-Download fehl (kein Internet,
Firmen-Firewall), fällt die Suche automatisch und ohne Fehlermeldung auf die
SQL-Volltextsuche zurück – ebenso, wenn die Vektorsuche zwar lief, aber
(nach dem Relevanz-Filter) NICHTS liefert: kurze Rückfragen wie "Was war
nochmal mein Plan?" liegen mit dem kleinen Embedding-Modell oft semantisch
weit von der gemeinten Notiz entfernt, ein Schlüsselwort daraus ("Plan")
findet sie per Volltextsuche trotzdem. Die Volltextsuche sucht dabei
wortweise (nicht die ganze Frage als ein Textblock) über Titel, Inhalt UND
Tags. Aufrufer bemerken den Unterschied zwischen den beiden Suchwegen nicht,
nur die Trefferqualität ändert sich. Jeder Treffer bekommt zusätzlich ein
``age``-Feld ("vor 3 Monaten") – macht Vault-Kontext im Chat als **proaktives
Wiederfinden** erkennbar statt als anonymen Suchtreffer.
"""

from __future__ import annotations

import asyncio
import json
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
_CREATED_RE = re.compile(r"^created:\s*(.+)$", re.MULTILINE)

#: Maximale Chroma-Distanz (Standard-Embedding-Funktion), ab der ein
#: Vektortreffer noch als thematisch relevant gilt statt verworfen zu werden
#: – siehe Docstring von ``MemoryEngine._semantic_search``.
_MAX_SEMANTIC_DISTANCE = 1.1

#: Kurze, häufige deutsche Füll-/Fragewörter – tragen selbst keine Bedeutung
#: und würden als Volltext-Suchwort nur Zufallstreffer erzeugen (fast jede
#: Notiz enthält irgendwo "ist" oder "und"). Siehe ``_search_tokens``.
_STOPWORDS = frozenset(
    "was wie wer wo wann warum welche welcher welches der die das den dem "
    "des und oder ist sind war waren wird werden ein eine einen einer mein "
    "meine meinen meiner dein deine noch mal nochmal auch ich du er sie es "
    "wir ihr hat habe haben für mit auf im in zu von an bei nach vor über "
    "unter sich nicht".split()
)


def _search_tokens(query: str) -> list[str]:
    """Zerlegt eine Suchanfrage in bedeutungstragende Wörter.

    Eine ganze Frage wie "Was war nochmal mein Plan?" taucht so gut wie nie
    wortgleich in einer Notiz auf – ein einzelnes Schlüsselwort daraus
    ("Plan", z. B. als Tag gesetzt) dagegen schon eher. Kurze Wörter (< 3
    Zeichen) und häufige Füllwörter werden verworfen, damit die
    Volltextsuche nicht auf bedeutungslosen Wörtern anschlägt.
    """
    words = re.findall(r"\w+", query.lower(), re.UNICODE)
    return [w for w in words if len(w) >= 3 and w not in _STOPWORDS]


def _slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.strip()).strip("-")
    return slug or "notiz"


def _age_phrase(created_at: float) -> str:
    """Natürlichsprachliche Zeitangabe ("vor 3 Monaten") aus einem
    Unix-Timestamp – macht einen Suchtreffer als proaktives Wiederfinden
    erkennbar statt als anonymes Ergebnis."""
    days = max(0.0, (time.time() - created_at) / 86400)
    if days < 1:
        return "heute"
    if days < 2:
        return "gestern"
    if days < 14:
        n = int(days)
        return f"vor {n} Tag" + ("" if n == 1 else "en")
    if days < 60:
        n = int(days / 7)
        return f"vor {n} Woche" + ("" if n == 1 else "n")
    if days < 365:
        n = int(days / 30)
        return f"vor {n} Monat" + ("" if n == 1 else "en")
    n = int(days / 365)
    return f"vor {n} Jahr" + ("" if n == 1 else "en")


def _existing_created(path: Path) -> str | None:
    """Liest ``created`` aus dem Frontmatter einer bereits vorhandenen Notiz.

    Wird eine Notiz überschrieben (z. B. ein Plan, dessen Schritte sich
    ändern), soll ``created`` stabil bleiben statt bei jedem Schreiben auf
    "jetzt" zu springen – sonst würde der Vault fälschlich behaupten, jede
    aktualisierte Notiz sei gerade eben neu entstanden.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _CREATED_RE.search(text)
    return match.group(1).strip() if match else None


class MemoryEngine(BaseEngine):
    """Schreibt und findet Markdown-Notizen im Obsidian-Vault."""

    name = "memory"

    async def start(self) -> None:
        self._running = True
        self.vault = self.config.vault_path
        self.vault.mkdir(parents=True, exist_ok=True)
        for category in CATEGORIES:
            (self.vault / category).mkdir(exist_ok=True)

        self._chroma_collection = None
        self._chroma_init_error: str | None = None

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
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._db.commit()

        self.bus.subscribe("memory.note", self.handle)
        self.bus.subscribe("memory.search", self._on_search)
        self.bus.subscribe("memory.kv.set", self._on_kv_set)
        self.bus.subscribe("memory.kv.get", self._on_kv_get)
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
        now_ts = time.time()

        # Upsert per Pfad: derselbe Titel+Kategorie ergibt denselben Pfad
        # (siehe _write_note) – ohne das DELETE würde jede Aktualisierung
        # einer bestehenden Notiz (z. B. ein fortschreitender Plan) einen
        # zusätzlichen, veralteten Index-Eintrag anhäufen statt den
        # bestehenden zu ersetzen.
        self._db.execute("DELETE FROM notes WHERE path = ?", (str(path),))
        self._db.execute(
            "INSERT INTO notes (title, category, tags, path, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, category, ",".join(tags), str(path), content, now_ts),
        )
        self._db.commit()

        # Vektor-Index bestenfalls aktuell halten (dieselbe Pfad-als-ID-
        # Upsert-Logik wie oben) – schlägt das fehl (kein ChromaDB, Modell-
        # Download nicht möglich), ist die Notiz trotzdem gespeichert; nur
        # die Vektorsuche fällt für diese Notiz auf Volltextsuche zurück.
        collection = await self._ensure_chroma()
        if collection is not None:
            try:
                await asyncio.to_thread(
                    collection.upsert,
                    ids=[str(path)],
                    documents=[f"{title}\n\n{content}"[:8000]],
                    metadatas=[{"title": title, "category": category, "created_at": now_ts}],
                )
            except Exception:  # noqa: BLE001
                self.log.exception("Vektor-Index-Update fehlgeschlagen (Notiz trotzdem gespeichert)")

        await self.emit("memory.saved", {"title": title, "category": category, "path": str(path)})

    async def _on_search(self, event: Event) -> None:
        """Sucht passende Notizen (``memory.search``) – semantisch über
        ChromaDB, wenn verfügbar, sonst Volltextsuche über den SQLite-Index."""
        query = (event.data.get("query") or "").strip()
        request_id = event.data.get("id", "")

        results = await self._semantic_search(query)
        # Nicht nur bei fehlender Vektorsuche (None) auf Volltext zurückfallen,
        # sondern auch, wenn sie zwar lief, aber (nach dem Distanz-Filter)
        # NICHTS liefert (leere Liste): kurze Rückfragen wie "Was war nochmal
        # mein Plan?" liegen mit dem kleinen Embedding-Modell oft weit von der
        # eigentlich gemeinten Notiz entfernt, obwohl ein Schlüsselwort
        # ("Plan", als Tag gesetzt) sie per Volltextsuche trivial finden würde.
        if not results:
            results = self._fulltext_search(query)

        await self.emit("memory.result", {"id": request_id, "query": query, "results": results})

    async def _semantic_search(self, query: str) -> list[dict] | None:
        """Vektorsuche über ChromaDB. Gibt ``None`` zurück, wenn nicht
        verfügbar/fehlgeschlagen – Aufrufer soll dann auf ``_fulltext_search``
        zurückfallen, statt ohne Ergebnis zu bleiben.

        Wichtig: ``collection.query`` liefert immer die ``n_results``
        NÄCHSTEN Nachbarn zurück, unabhängig davon, wie (un)ähnlich sie
        tatsächlich sind – bei nur einer Notiz im Vault käme selbst eine
        völlig themenfremde Anfrage als "Treffer" zurück. Deshalb werden
        Treffer mit einer Distanz über ``_MAX_SEMANTIC_DISTANCE`` verworfen
        (empirisch kalibriert: thematisch verwandte Anfragen lagen bei
        Tests durchweg unter ~1.0, unverwandte durchweg über ~1.4)."""
        if not query:
            return None
        collection = await self._ensure_chroma()
        if collection is None:
            return None
        try:
            raw = await asyncio.to_thread(collection.query, query_texts=[query], n_results=10)
        except Exception:  # noqa: BLE001
            self.log.exception("Vektorsuche fehlgeschlagen, Fallback auf Volltextsuche")
            return None
        ids = (raw.get("ids") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        return [
            {
                "title": (meta or {}).get("title", ""),
                "category": (meta or {}).get("category", ""),
                "path": path,
                "age": _age_phrase((meta or {}).get("created_at") or time.time()),
            }
            for path, meta, distance in zip(ids, metadatas, distances)
            if distance <= _MAX_SEMANTIC_DISTANCE
        ]

    def _fulltext_search(self, query: str) -> list[dict]:
        """SQL-Volltextsuche über Titel/Inhalt/Tags – wortweise statt als
        Ganzes: eine komplette Frage stimmt so gut wie nie wortgleich mit
        einer Notiz überein, ein einzelnes Schlüsselwort (auch als Tag
        gesetzt, z. B. "plan") eher (siehe ``_search_tokens``). Bleiben nach
        dem Filtern keine bedeutungstragenden Wörter übrig (z. B. eine sehr
        kurze Anfrage), wird die Anfrage als Ganzes als Fallback verwendet."""
        tokens = _search_tokens(query) or ([query.strip()] if query.strip() else [])
        if not tokens:
            return []
        conditions = []
        params: list[str] = []
        for token in tokens:
            conditions.append("(title LIKE ? OR content LIKE ? OR tags LIKE ?)")
            like = f"%{token}%"
            params += [like, like, like]
        rows = self._db.execute(
            "SELECT title, category, path, created_at FROM notes WHERE "
            + " OR ".join(conditions)
            + " ORDER BY created_at DESC LIMIT 10",
            params,
        ).fetchall()
        return [
            {"title": r[0], "category": r[1], "path": r[2], "age": _age_phrase(r[3])} for r in rows
        ]

    async def _ensure_chroma(self):  # noqa: ANN201
        """Lazy: initialisiert die ChromaDB-Kollektion für semantische Suche.

        Best-effort: Fehlt das Paket (kein ``pip install -e ".[vector]"``)
        oder schlägt der einmalige Embedding-Modell-Download fehl (kein
        Internet, Firmen-Firewall), bleibt die Vektorsuche einfach aus –
        ``memory.search`` fällt automatisch auf die SQL-Volltextsuche zurück,
        kein Absturz, keine Sonderbehandlung für Aufrufer nötig. Fehler wird
        genau einmal gecached (nicht bei jeder Anfrage neu versucht).
        """
        if self._chroma_collection is not None or self._chroma_init_error is not None:
            return self._chroma_collection
        try:
            import chromadb

            client = await asyncio.to_thread(
                chromadb.PersistentClient, path=str(self.config.db_path.parent / "chroma")
            )
            self._chroma_collection = await asyncio.to_thread(
                client.get_or_create_collection, "aphelios_vault"
            )
            self.log.info("Vektorsuche aktiv (ChromaDB)")
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Vektorsuche nicht verfügbar, Fallback auf Volltextsuche: %s", exc)
            self._chroma_init_error = str(exc)
        return self._chroma_collection

    async def _on_kv_set(self, event: Event) -> None:
        """Speichert einen beliebigen, JSON-serialisierbaren Wert unter ``key``."""
        key = (event.data.get("key") or "").strip()
        if not key:
            return
        value = json.dumps(event.data.get("value"))
        self._db.execute(
            "INSERT INTO kv (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, time.time()),
        )
        self._db.commit()

    async def _on_kv_get(self, event: Event) -> None:
        """Liest einen zuvor per ``memory.kv.set`` gespeicherten Wert zurück."""
        key = (event.data.get("key") or "").strip()
        request_id = event.data.get("id", "")
        row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        value = json.loads(row[0]) if row else None
        await self.emit("memory.kv.result", {"id": request_id, "key": key, "value": value})

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
        created = _existing_created(path) or now
        frontmatter = [
            "---",
            f"title: {title}",
            f"category: {category}",
            f"created: {created}",
        ]
        if created != now:
            frontmatter.append(f"updated: {now}")
        frontmatter += [
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
