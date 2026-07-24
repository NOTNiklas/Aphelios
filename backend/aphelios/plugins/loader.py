"""PluginLoader – entdeckt und lädt Plugins aus den Kategorie-Ordnern.

Durchsucht ``<plugins_root>/<Kategorie>/<plugin>/manifest.json``, validiert
jedes Manifest, importiert den Entry-Point und instanziiert das Plugin.
Ungültige oder deaktivierte Plugins werden übersprungen und protokolliert.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

from aphelios.core.config import Config
from aphelios.core.event_bus import EventBus
from aphelios.plugins.base import Plugin, PluginManifest

logger = logging.getLogger("aphelios.plugins")


class PluginLoader:
    """Findet, validiert und lädt Plugins aus dem Plugin-Verzeichnis."""

    def __init__(self, bus: EventBus, config: Config, plugins_root: Path) -> None:
        self.bus = bus
        self.config = config
        self.root = plugins_root
        self.loaded: list[Plugin] = []

    def discover(self) -> list[PluginManifest]:
        """Liest alle ``manifest.json`` unter dem Plugin-Root ein."""
        manifests: list[PluginManifest] = []
        if not self.root.exists():
            logger.info("Plugin-Verzeichnis %s existiert nicht – überspringe", self.root)
            return manifests
        for manifest_path in self.root.glob("*/*/manifest.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = PluginManifest.from_dict(data)
                manifest._path = manifest_path.parent  # type: ignore[attr-defined]
                manifests.append(manifest)
            except Exception:  # noqa: BLE001
                logger.exception("Ungültiges Manifest: %s", manifest_path)
        return manifests

    async def load_all(self) -> list[Plugin]:
        """Lädt alle aktivierten, gültigen Plugins."""
        for manifest in self.discover():
            if not manifest.enabled:
                logger.info("Plugin %s ist deaktiviert – übersprungen", manifest.name)
                continue
            plugin = self._instantiate(manifest)
            if plugin is None:
                continue
            try:
                await plugin.on_load()
                self.loaded.append(plugin)
                logger.info("Plugin geladen: %s v%s (%s)",
                            manifest.name, manifest.version, manifest.category)
            except Exception:  # noqa: BLE001
                logger.exception("Plugin %s konnte nicht initialisiert werden", manifest.name)
        return self.loaded

    async def unload_all(self) -> None:
        for plugin in self.loaded:
            try:
                await plugin.on_unload()
            except Exception:  # noqa: BLE001
                logger.exception("Fehler beim Entladen von %s", plugin.manifest.name)
        self.loaded.clear()

    def _instantiate(self, manifest: PluginManifest) -> Plugin | None:
        """Importiert ``datei.py:Klasse`` relativ zum Plugin-Ordner."""
        try:
            file_part, _, class_name = manifest.entrypoint.partition(":")
            plugin_dir: Path = getattr(manifest, "_path")  # type: ignore[assignment]
            module_path = plugin_dir / file_part
            spec = importlib.util.spec_from_file_location(
                f"aphelios_plugin_{manifest.name}", module_path
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Kann {module_path} nicht laden")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            plugin_cls = getattr(module, class_name)
            return plugin_cls(self.bus, self.config, manifest)
        except Exception:  # noqa: BLE001
            logger.exception("Entry-Point von %s konnte nicht geladen werden", manifest.name)
            return None
