"""EngineManager – registriert Engines und steuert ihren Lebenszyklus.

Jede Engine läuft unabhängig. Der Manager startet und stoppt alle gemeinsam
und bietet einen Überblick über ihren Status (für den Health-Check / das HUD).
"""

from __future__ import annotations

import asyncio
import logging

from aphelios.core.engine import BaseEngine

logger = logging.getLogger("aphelios.manager")


class EngineManager:
    """Verwaltet die Menge aller aktiven Engines."""

    def __init__(self) -> None:
        self._engines: dict[str, BaseEngine] = {}

    def register(self, engine: BaseEngine) -> None:
        """Fügt eine Engine hinzu (Name muss eindeutig sein)."""
        if engine.name in self._engines:
            raise ValueError(f"Engine mit Namen {engine.name!r} ist bereits registriert")
        self._engines[engine.name] = engine
        logger.debug("registered engine %s", engine.name)

    def get(self, name: str) -> BaseEngine | None:
        return self._engines.get(name)

    async def start_all(self) -> None:
        """Startet alle Engines nebenläufig."""
        logger.info("starting %d engine(s)", len(self._engines))
        results = await asyncio.gather(
            *(self._safe_start(engine) for engine in self._engines.values()),
            return_exceptions=True,
        )
        for engine, result in zip(self._engines.values(), results):
            if isinstance(result, Exception):
                logger.error("engine %s failed to start: %r", engine.name, result)

    async def stop_all(self) -> None:
        """Stoppt alle Engines nebenläufig."""
        logger.info("stopping %d engine(s)", len(self._engines))
        await asyncio.gather(
            *(self._safe_stop(engine) for engine in self._engines.values()),
            return_exceptions=True,
        )

    async def _safe_start(self, engine: BaseEngine) -> None:
        await engine.start()
        engine._running = True  # noqa: SLF001 – Manager darf den Zustand setzen
        logger.info("engine %s online", engine.name)

    async def _safe_stop(self, engine: BaseEngine) -> None:
        try:
            await engine.stop()
        finally:
            engine._running = False  # noqa: SLF001

    def status(self) -> dict[str, str]:
        """Status aller Engines: ``{name: "online"|"offline"}``."""
        return {name: engine.status for name, engine in self._engines.items()}

    @property
    def engines(self) -> list[BaseEngine]:
        return list(self._engines.values())
