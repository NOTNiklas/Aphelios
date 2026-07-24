"""Einstiegspunkt von APHELIOS.

Startet den API-Server (FastAPI + WebSocket), der seinerseits den EngineManager
und alle Engines hochfährt.

Aufruf::

    python -m aphelios
"""

from __future__ import annotations

import logging

import uvicorn

from aphelios.api import create_app
from aphelios.core.config import Config


def run() -> None:
    config = Config.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    banner(config)
    app = create_app(config)
    uvicorn.run(app, host=config.api_host, port=config.api_port, log_level="warning")


def banner(config: Config) -> None:
    ai = "Claude API" if config.has_anthropic else "Fallback-Modus (kein API-Key)"
    print(
        "\n".join(
            [
                "",
                "  ⬡  A P H E L I O S   —   Alpha 1.0",
                "  ─────────────────────────────────────",
                f"  API      http://{config.api_host}:{config.api_port}",
                f"  AI       {ai}",
                f"  Vault    {config.vault_path.resolve()}",
                "  Status   ONLINE",
                "",
            ]
        )
    )


if __name__ == "__main__":
    run()
