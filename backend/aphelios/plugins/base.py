"""Plugin-Basisklasse und Manifest-Schema.

Jedes Feature von APHELIOS kann als Plugin ergänzt werden. Ein Plugin besteht
aus einer ``manifest.json`` und einer Python-Klasse, die von ``Plugin`` erbt.
Siehe ``docs/plugins.md``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus

#: Erlaubte Plugin-Kategorien (entsprechen den Ordnern unter ``/plugins``).
CATEGORIES = [
    "Core",
    "Voice",
    "Memory",
    "Browser",
    "Windows",
    "Developer",
    "Office",
    "AI",
    "Automation",
    "Security",
    "Vision",
    "Music",
    "Calendar",
    "Mail",
    "HomeDesk",
    "SmartHome",
]


@dataclass(slots=True)
class PluginManifest:
    """Validiertes Abbild einer ``manifest.json``."""

    name: str
    version: str
    category: str
    entrypoint: str  # "datei.py:KlassenName"
    description: str = ""
    permissions: list[str] = field(default_factory=list)
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "PluginManifest":
        missing = [k for k in ("name", "version", "category", "entrypoint") if k not in data]
        if missing:
            raise ValueError(f"Manifest unvollständig, fehlende Felder: {missing}")
        if data["category"] not in CATEGORIES:
            raise ValueError(f"Unbekannte Kategorie: {data['category']!r}")
        return cls(
            name=data["name"],
            version=data["version"],
            category=data["category"],
            entrypoint=data["entrypoint"],
            description=data.get("description", ""),
            permissions=list(data.get("permissions", [])),
            enabled=bool(data.get("enabled", True)),
        )


class Plugin(ABC):
    """Basisklasse für alle Plugins.

    Bekommt beim Laden den EventBus und die Config injiziert und kann darüber
    Topics abonnieren und Events publizieren – genau wie eine Engine, aber
    unabhängig ergänzbar.
    """

    def __init__(self, bus: EventBus, config: Config, manifest: PluginManifest) -> None:
        self.bus = bus
        self.config = config
        self.manifest = manifest

    @abstractmethod
    async def on_load(self) -> None:
        """Wird nach dem Laden aufgerufen – hier Topics abonnieren."""

    async def on_unload(self) -> None:
        """Optional: sauber aufräumen (Standard: no-op)."""

    async def emit(self, topic: str, data: dict | None = None) -> None:
        await self.bus.publish(Event(topic, data or {}, source=f"plugin:{self.manifest.name}"))
