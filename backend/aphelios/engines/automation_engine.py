"""AutomationEngine – PowerShell-Ausführung, Datei-Operationen, Programme
starten/schließen (Alpha 1.2, erste Ausbaustufe).

**Programme per Name finden:** ``open_app`` erwartet nicht zwingend einen
exakten, PATH-auflösbaren Namen (``os.startfile`` allein findet z. B.
"notepad", aber nicht "Obsidian" – die meisten installierten Apps liegen
nicht im PATH). Stattdessen wird zuerst das Windows-Startmenü/der Desktop
nach einer passenden Verknüpfung (``.lnk``/``.exe``) durchsucht – demselben
Mechanismus, den das native Windows-Startmenü beim Tippen nutzt. Gefunden,
wird der aufgelöste Pfad gestartet (und im Bestätigungsdialog transparent
angezeigt); sonst greift der bisherige Fallback auf den rohen Namen (PATH/
App-Paths via ``os.startfile``).

**Grundsatz:** Alles außer reinem Lesen (`list_dir`, `find_files`,
`downloads`) läuft zwingend über das ``SecurityGate`` – siehe
``docs/security.md``. Es gibt keinen Pfad, der eine schreibende/löschende
Aktion ohne ausdrückliche Nutzerbestätigung ausführt.

Auslösen im Chat (Slash-Befehle, direkt vom Nutzer getippt – **nicht** von
einer AI-Entscheidung ausgelöst, damit kein Prompt-Injection-Pfad zu echten
Systemaktionen führt):

    * ``/run <PowerShell-Befehl>``  – ``run_powershell``
    * ``/oeffne <Programmname>``    – ``open_app``
    * ``/schliesse <Programmname>`` – ``close_app``
    * ``/loesche <Pfad>``           – ``delete_path`` (Datei oder Ordner)
    * ``/downloads``                – listet den Downloads-Ordner (nur lesend)

**Bewusst NICHT in dieser ersten Ausbaustufe:**

- **Programme installieren/deinstallieren** – der Mechanismus (winget? eine
  feste Allowlist? beliebige Installer-Pfade?) ist eine echte
  Sicherheitsabwägung, keine rein technische Entscheidung – siehe
  ``ROADMAP.md`` Alpha 1.2. Braucht erst eine bewusste Entscheidung des
  Nutzers, genau wie WhatsApp in ``docs/integrations.md``.
- **pywinauto-Fensterinteraktion** – erfordert eine echte, laufende
  Windows-Desktop-Sitzung zum Testen (UI Automation), die in dieser
  Entwicklungsumgebung (Linux, ohne Display) grundsätzlich nicht verfügbar
  ist. Blind implementieren, ohne es je laufen zu sehen, wäre unseriös.

Bus-Schnittstelle:
    * ``automation.request`` (in) – ``{id, action, ...}``
    * ``chat.token`` / ``chat.response`` (out) – Rückmeldung im Chat
"""

from __future__ import annotations

import asyncio
import difflib
import os
import re
import shutil
import sys
from pathlib import Path

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.core.security import RiskLevel

#: APHELIOS zielt auf Windows (siehe README); auf anderen Plattformen (z. B.
#: dieser Linux-Entwicklungsumgebung) geben PowerShell/Programm-Aktionen
#: einen ehrlichen "nicht unterstützt"-Hinweis zurück statt zu crashen –
#: dasselbe Muster wie GPU/Temperatur in der SystemEngine.
IS_WINDOWS = sys.platform == "win32"

#: Befehlsmuster, die trotz "nur ein Shell-Befehl" besonders zerstörerisch
#: sind (Formatierung, Registry-Löschung, Deinstallation, Neustart/Shutdown,
#: Wiederherstellungspunkte deaktivieren) – dafür zusätzlich ein Warnhinweis
#: (RiskLevel.DANGEROUS statt CONFIRM).
_DANGEROUS_PATTERN = re.compile(
    r"remove-item\s+.*-recurse|format-volume|clear-disk|reg(?:\.exe)?\s+delete|"
    r"stop-computer|restart-computer|uninstall|bcdedit|diskpart|"
    r"set-executionpolicy|disable-computerrestore|net\s+user",
    re.IGNORECASE,
)


def classify_powershell(command: str) -> RiskLevel:
    """Klassifiziert einen PowerShell-Befehl nach Risiko.

    Arbiträre Shell-Ausführung ist niemals ``SAFE`` – nur die Frage ist, ob
    ``CONFIRM`` reicht oder ein zusätzlicher Warnhinweis (``DANGEROUS``)
    angebracht ist.
    """
    if _DANGEROUS_PATTERN.search(command):
        return RiskLevel.DANGEROUS
    return RiskLevel.CONFIRM


#: Dateiendungen, die als "startbares Programm" zählen, wenn nach einem
#: Anzeigenamen gesucht wird (Verknüpfung oder direkte ausführbare Datei).
_APP_EXTENSIONS = (".lnk", ".exe")


def _shortcut_search_dirs() -> list[Path]:
    """Verzeichnisse, in denen Windows Programm-Verknüpfungen ablegt.

    Dieselben Orte, die auch das native Windows-Startmenü durchsucht:
    Start-Menü (pro Nutzer + für alle Nutzer) und Desktop (pro Nutzer +
    öffentlich). Über Umgebungsvariablen aufgelöst statt hartcodierter
    Pfade – funktioniert dadurch unter jedem Nutzerkonto und lässt sich in
    Tests per ``monkeypatch.setenv`` gezielt auf ein Testverzeichnis lenken.
    """
    env_subpaths = [
        ("APPDATA", "Microsoft/Windows/Start Menu/Programs"),
        ("PROGRAMDATA", "Microsoft/Windows/Start Menu/Programs"),
        ("USERPROFILE", "Desktop"),
        ("PUBLIC", "Desktop"),
    ]
    dirs: list[Path] = []
    for var, sub in env_subpaths:
        base = os.environ.get(var)
        if base:
            candidate = Path(base) / sub
            if candidate.is_dir():
                dirs.append(candidate)
    return dirs


def _iter_known_apps() -> list[Path]:
    """Alle gefundenen Programm-Verknüpfungen/.exe-Dateien (rekursiv)."""
    found: list[Path] = []
    for directory in _shortcut_search_dirs():
        for path in directory.rglob("*"):
            if path.suffix.lower() in _APP_EXTENSIONS:
                found.append(path)
    return found


def find_app_path(name: str) -> Path | None:
    """Löst einen Anzeigenamen (z. B. "Obsidian") zu einer startbaren Datei auf.

    Exakter Treffer (Groß-/Kleinschreibung egal) gewinnt sofort; sonst der
    Teilstring-Treffer mit dem kürzesten (also spezifischsten) Namen. Gibt
    ``None`` zurück, wenn nichts passt – Aufrufer fallen dann auf den rohen
    Namen zurück (funktioniert weiter für PATH-/App-Paths-auflösbare Namen
    wie "notepad").
    """
    lowered = name.strip().lower()
    if not lowered:
        return None
    best: tuple[int, Path] | None = None
    for path in _iter_known_apps():
        stem = path.stem.lower()
        if stem == lowered:
            return path
        if lowered in stem:
            score = len(stem) - len(lowered)
            if best is None or score < best[0]:
                best = (score, path)
    return best[1] if best else None


def find_similar_app_names(name: str, limit: int = 5) -> list[str]:
    """"Meintest du …?"-Vorschläge, wenn ``find_app_path`` nichts fand."""
    names = sorted({path.stem for path in _iter_known_apps()})
    return difflib.get_close_matches(name, names, n=limit, cutoff=0.4)


def _human_size(path: Path) -> str:
    if path.is_dir():
        return "Ordner"
    size = float(path.stat().st_size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.0f} TB"


class AutomationEngine(BaseEngine):
    """Führt strukturierte System-Aktionen aus – jede schreibende/löschende
    Aktion zwingend über das SecurityGate bestätigt."""

    name = "automation"

    async def start(self) -> None:
        self._running = True
        self.bus.subscribe("automation.request", self.handle)

    async def handle(self, event: Event) -> None:
        action = event.data.get("action", "")
        request_id = event.data.get("id", "")
        handler = self._ACTIONS.get(action)
        if handler is None:
            await self._reply(request_id, f"Unbekannte Automatisierungs-Aktion: {action!r}")
            return
        try:
            reply = await handler(self, event.data)
        except Exception as exc:  # noqa: BLE001 – Fehlerursache soll im Chat sichtbar bleiben
            self.log.exception("Automatisierung fehlgeschlagen: %s", action)
            reply = f"Fehlgeschlagen: {exc}"[:300]
        await self._reply(request_id, reply)

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})

    # -- PowerShell ---------------------------------------------------------
    async def _run_powershell(self, data: dict) -> str:
        command = (data.get("command") or "").strip()
        if not command:
            return "Kein Befehl angegeben."
        if not IS_WINDOWS:
            return (
                "PowerShell-Ausführung ist nur unter Windows verfügbar "
                f"(APHELIOS' Ziel-Plattform). Befehl wäre gewesen: {command}"
            )

        level = classify_powershell(command)
        allowed = await self.security.request(
            action="PowerShell ausführen",
            target=command,
            level=level,
            reason="Direkte Shell-Ausführung kann das System verändern.",
        )
        if not allowed:
            return "Abgelehnt – der Befehl wurde nicht ausgeführt."

        proc = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        output = (stdout or stderr).decode("utf-8", errors="replace").strip()
        return output[:1500] or "Befehl ausgeführt (keine Ausgabe)."

    # -- Programme ------------------------------------------------------------
    async def _open_app(self, data: dict) -> str:
        name = (data.get("name") or "").strip()
        if not name:
            return "Kein Programmname angegeben."
        if not IS_WINDOWS:
            return f"Programme starten ist nur unter Windows verfügbar. Gestartet wäre: {name}"

        # Erst auflösen (Startmenü/Desktop durchsuchen), DANN bestätigen lassen –
        # damit der Bestätigungsdialog den echten Pfad zeigt, nicht nur den
        # eingetippten Namen. Kein Treffer → Fallback auf den rohen Namen
        # (funktioniert weiter für PATH-/App-Paths-Namen wie "notepad").
        resolved = find_app_path(name)
        target = str(resolved) if resolved else name

        allowed = await self.security.request(
            action="Programm starten",
            target=target,
            level=RiskLevel.CONFIRM,
            reason="Startet ein Programm auf dem System.",
        )
        if not allowed:
            return "Abgelehnt."
        try:
            os.startfile(target)  # noqa: S606 – bewusst, erst nach Nutzerbestätigung
        except OSError as exc:
            suggestions = find_similar_app_names(name)
            hint = f" Meintest du: {', '.join(suggestions)}?" if suggestions else ""
            return f"Konnte {name!r} nicht starten: {exc}.{hint}"
        return f"{name} gestartet (über {resolved.name})." if resolved else f"{name} gestartet."

    async def _close_app(self, data: dict) -> str:
        import psutil

        name = (data.get("name") or "").strip()
        if not name:
            return "Kein Programmname angegeben."
        allowed = await self.security.request(
            action="Programm schließen",
            target=name,
            level=RiskLevel.CONFIRM,
            reason="Beendet einen laufenden Prozess.",
        )
        if not allowed:
            return "Abgelehnt."
        closed = 0
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower().startswith(name.lower()):
                try:
                    proc.terminate()
                    closed += 1
                except psutil.Error:
                    pass
        if closed:
            return f"{closed} Prozess(e) mit Namen ~{name!r} beendet."
        return f"Kein laufender Prozess namens {name!r} gefunden."

    # -- Datei-Operationen ------------------------------------------------------
    async def _list_dir(self, data: dict) -> str:
        path = Path(data.get("path") or ".").expanduser()
        if not path.exists():
            return f"Pfad nicht gefunden: {path}"
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
        listing = "\n".join(entries[:50])
        return f"{len(entries)} Eintrag/Einträge in {path}:\n{listing}"

    async def _find_files(self, data: dict) -> str:
        path = Path(data.get("path") or ".").expanduser()
        pattern = data.get("pattern") or "*"
        if not path.exists():
            return f"Pfad nicht gefunden: {path}"
        matches = [str(p) for p in path.rglob(pattern)][:50]
        if not matches:
            return f"Keine Treffer für {pattern!r} in {path}."
        return f"{len(matches)} Treffer für {pattern!r} in {path}:\n" + "\n".join(matches)

    async def _create_folder(self, data: dict) -> str:
        raw = (data.get("path") or "").strip()
        if not raw:
            return "Kein Pfad angegeben."
        path = Path(raw).expanduser()
        allowed = await self.security.request(
            action="Ordner erstellen",
            target=str(path),
            level=RiskLevel.CONFIRM,
            reason="Legt einen neuen Ordner auf der Festplatte an.",
        )
        if not allowed:
            return "Abgelehnt."
        path.mkdir(parents=True, exist_ok=True)
        return f"Ordner erstellt: {path}"

    async def _create_file(self, data: dict) -> str:
        raw = (data.get("path") or "").strip()
        if not raw:
            return "Kein Pfad angegeben."
        path = Path(raw).expanduser()
        content = data.get("content") or ""
        allowed = await self.security.request(
            action="Datei erstellen",
            target=str(path),
            level=RiskLevel.CONFIRM,
            reason="Legt eine neue Datei auf der Festplatte an.",
        )
        if not allowed:
            return "Abgelehnt."
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Datei erstellt: {path}"

    async def _move_file(self, data: dict) -> str:
        raw_src, raw_dst = (data.get("src") or "").strip(), (data.get("dst") or "").strip()
        if not raw_src or not raw_dst:
            return "Quelle oder Ziel fehlt."
        src, dst = Path(raw_src).expanduser(), Path(raw_dst).expanduser()
        if not src.exists():
            return f"Quelle nicht gefunden: {src}"
        allowed = await self.security.request(
            action="Datei verschieben",
            target=f"{src} → {dst}",
            level=RiskLevel.CONFIRM,
            reason="Verschiebt oder benennt eine Datei/einen Ordner um.",
        )
        if not allowed:
            return "Abgelehnt."
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Verschoben: {src} → {dst}"

    async def _delete_path(self, data: dict) -> str:
        raw = (data.get("path") or "").strip()
        if not raw:
            return "Kein Pfad angegeben."
        path = Path(raw).expanduser()
        if not path.exists():
            return f"Pfad nicht gefunden: {path}"
        allowed = await self.security.request(
            action="Löschen",
            target=str(path),
            level=RiskLevel.CONFIRM,
            reason="Löscht eine Datei oder einen Ordner (nicht rückgängig zu machen).",
        )
        if not allowed:
            return "Abgelehnt."
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return f"Gelöscht: {path}"

    async def _downloads(self, data: dict) -> str:
        downloads = Path.home() / "Downloads"
        if not downloads.exists():
            return f"Kein Downloads-Ordner gefunden unter {downloads}."
        entries = sorted(downloads.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        lines = [f"{p.name} ({_human_size(p)})" for p in entries[:20]]
        listing = "\n".join(lines) if lines else "(leer)"
        return f"{len(entries)} Eintrag/Einträge in {downloads}, neueste zuerst:\n{listing}"

    _ACTIONS = {
        "run_powershell": _run_powershell,
        "open_app": _open_app,
        "close_app": _close_app,
        "list_dir": _list_dir,
        "find_files": _find_files,
        "create_folder": _create_folder,
        "create_file": _create_file,
        "move_file": _move_file,
        "delete_path": _delete_path,
        "downloads": _downloads,
    }
