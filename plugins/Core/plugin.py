"""Beispiel-Plugin (Kategorie: Core).

Zeigt die minimale Struktur eines APHELIOS-Plugins. Zum Aktivieren:
``manifest.example.json`` nach ``manifest.json`` kopieren und ``enabled: true``
setzen – der PluginLoader entdeckt und lädt es dann automatisch.
"""

from __future__ import annotations

from aphelios.core.event_bus import Event
from aphelios.plugins.base import Plugin as BasePlugin


class Plugin(BasePlugin):
    """Beantwortet ``core.ping`` mit einem ``core.pong``-Event."""

    async def on_load(self) -> None:
        self.bus.subscribe("core.ping", self._on_ping)

    async def _on_ping(self, event: Event) -> None:
        await self.emit("core.pong", {"echo": event.data})
