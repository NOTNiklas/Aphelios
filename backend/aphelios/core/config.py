"""Konfiguration – lädt Einstellungen aus Umgebungsvariablen / ``.env``.

Alle Schlüssel sind in ``.env.example`` dokumentiert. Ohne ``ANTHROPIC_API_KEY``
läuft APHELIOS im Fallback-Modus.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # dotenv ist optional, aber empfohlen
    from dotenv import load_dotenv

    # Lädt eine .env aus dem Projekt-Root (zwei Ebenen über dieser Datei) bzw. cwd.
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[3] / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            break
except ImportError:  # pragma: no cover
    pass


def _get(name: str, default: str) -> str:
    """Liest eine Umgebungsvariable und entfernt umschließende Leer-/Anführungszeichen.

    Häufiger Stolperstein: ``KEY= wert`` (Leerzeichen nach dem ``=``) oder
    ``KEY="wert"`` machen z. B. einen API-Key sonst unbemerkt ungültig – die
    Anfrage schlägt dann fehl und die App fällt lautlos in den Fallback-Modus.
    """
    value = os.environ.get(name, default).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


@dataclass(slots=True)
class Config:
    """Zentrale, unveränderliche Laufzeitkonfiguration."""

    # --- AI-Provider ---
    ai_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # --- Memory ---
    vault_path: Path = Path("./vault")
    db_path: Path = Path("./data/aphelios.sqlite")

    # --- System-Monitoring ---
    stats_interval: float = 2.0

    # --- Wetter (Open-Meteo, kein API-Key nötig) ---
    weather_city: str = "Berlin"
    weather_interval: float = 900.0

    # --- Google (Gmail + Kalender, eigener OAuth-Client nötig) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_token_path: Path = Path("./data/google_token.json")
    google_poll_interval: float = 300.0

    # --- Sprache (Alpha 1.3, optional: lokale Whisper-STT + Piper-TTS) ---
    #: Piper-Sprachmodell (.onnx-Datei); ``None`` = TTS bleibt aus, Frontend
    #: fällt automatisch auf die Browser-Stimme zurück. Modelle:
    #: https://github.com/rhasspy/piper/blob/master/VOICES.md
    #: Bewusst ``Path | None`` statt ``Path("")``: ``Path("")`` normalisiert
    #: sich zu ``Path(".")`` (aktuelles Verzeichnis), das existiert immer –
    #: eine reine Existenzprüfung würde "nicht konfiguriert" dadurch nie
    #: erkennen.
    piper_model_path: Path | None = None
    #: faster-whisper-Modellgröße ("tiny"/"base"/"small"/"medium"/"large-v3")
    #: – wird beim ersten Gebrauch automatisch heruntergeladen und lokal
    #: zwischengespeichert (Hugging Face Hub).
    whisper_model: str = "base"
    whisper_device: str = "cpu"

    # --- API-Server ---
    api_host: str = "127.0.0.1"
    api_port: int = 8787
    cors_origin: str = "http://localhost:5173"

    # --- Verhalten ---
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        """Baut eine Config aus den Umgebungsvariablen (siehe ``.env.example``)."""
        return cls(
            ai_provider=_get("APHELIOS_AI_PROVIDER", "anthropic"),
            anthropic_api_key=_get("ANTHROPIC_API_KEY", ""),
            anthropic_model=_get("APHELIOS_ANTHROPIC_MODEL", "claude-opus-4-8"),
            openai_api_key=_get("OPENAI_API_KEY", ""),
            openai_model=_get("APHELIOS_OPENAI_MODEL", "gpt-4o"),
            ollama_host=_get("APHELIOS_OLLAMA_HOST", "http://localhost:11434"),
            ollama_model=_get("APHELIOS_OLLAMA_MODEL", "llama3.1"),
            vault_path=Path(_get("APHELIOS_VAULT_PATH", "./vault")),
            db_path=Path(_get("APHELIOS_DB_PATH", "./data/aphelios.sqlite")),
            stats_interval=float(_get("APHELIOS_STATS_INTERVAL", "2.0")),
            weather_city=_get("APHELIOS_WEATHER_CITY", "Berlin"),
            weather_interval=float(_get("APHELIOS_WEATHER_INTERVAL", "900")),
            google_client_id=_get("GOOGLE_CLIENT_ID", ""),
            google_client_secret=_get("GOOGLE_CLIENT_SECRET", ""),
            google_token_path=Path(_get("APHELIOS_GOOGLE_TOKEN_PATH", "./data/google_token.json")),
            google_poll_interval=float(_get("APHELIOS_GOOGLE_POLL_INTERVAL", "300")),
            piper_model_path=(
                Path(_raw_piper) if (_raw_piper := _get("APHELIOS_PIPER_MODEL_PATH", "")) else None
            ),
            whisper_model=_get("APHELIOS_WHISPER_MODEL", "base"),
            whisper_device=_get("APHELIOS_WHISPER_DEVICE", "cpu"),
            api_host=_get("APHELIOS_API_HOST", "127.0.0.1"),
            api_port=int(_get("APHELIOS_API_PORT", "8787")),
            cors_origin=_get("APHELIOS_CORS_ORIGIN", "http://localhost:5173"),
            log_level=_get("APHELIOS_LOG_LEVEL", "INFO").upper(),
        )

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_google(self) -> bool:
        """True, sobald ``scripts/google_auth.py`` einmalig erfolgreich lief."""
        return self.google_token_path.exists()

    @property
    def has_piper(self) -> bool:
        """True, sobald ein Piper-Sprachmodell konfiguriert ist (siehe docs/voice.md)."""
        return self.piper_model_path is not None and self.piper_model_path.exists()
