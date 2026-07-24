"""Plugin-System von APHELIOS: Basisklasse, Manifest-Schema und Loader."""

from aphelios.plugins.base import Plugin, PluginManifest
from aphelios.plugins.loader import PluginLoader

__all__ = ["Plugin", "PluginManifest", "PluginLoader"]
