"""Tests für die AutomationEngine (Alpha 1.2): Risiko-Klassifizierung,
Datei-Operationen (real, über tmp_path) und die SecurityGate-Integration
(Ablehnung MUSS die Aktion verhindern – das ist der ganze Sinn des Gates).

PowerShell-Ausführung und Programme starten sind unter Windows implementiert
(``os.startfile`` existiert unter Linux gar nicht) – hier über
``IS_WINDOWS``/``asyncio.create_subprocess_exec``/``os.startfile`` gemockt,
damit die eigentliche Logik (Risiko-Einstufung, Bestätigungs-Fluss,
Ausgabe-Verarbeitung) trotzdem ohne echte Windows-Maschine getestet wird.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import RiskLevel, SecurityGate
from aphelios.engines import automation_engine as automation_module
from aphelios.engines.automation_engine import AutomationEngine, classify_powershell


def _engine(bus: EventBus, timeout: float = 2.0) -> AutomationEngine:
    security = SecurityGate(bus, default_timeout=timeout)
    return AutomationEngine(bus, Config(), security)


def _auto_approve(bus: EventBus) -> None:
    async def approve(event: Event) -> None:
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve)


def _auto_deny(bus: EventBus) -> None:
    async def deny(event: Event) -> None:
        await bus.publish(Event("confirmation.deny", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", deny)


async def _run(engine: AutomationEngine, action: str, **data) -> str:
    responses: list[dict] = []
    engine.bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle(Event("automation.request", {"id": "t1", "action": action, **data}))
    return responses[-1]["text"]


# -- Risiko-Klassifizierung ---------------------------------------------------
def test_classify_powershell_flags_destructive_patterns_as_dangerous():
    assert classify_powershell("Remove-Item C:\\temp -Recurse -Force") == RiskLevel.DANGEROUS
    assert classify_powershell("Uninstall-Package Foo") == RiskLevel.DANGEROUS
    assert classify_powershell("Restart-Computer -Force") == RiskLevel.DANGEROUS


def test_classify_powershell_defaults_to_confirm():
    assert classify_powershell("Get-Process") == RiskLevel.CONFIRM
    assert classify_powershell("echo hallo") == RiskLevel.CONFIRM


# -- Unbekannte Aktion ---------------------------------------------------------
async def test_unknown_action_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "does_not_exist")
    assert "Unbekannte Automatisierungs-Aktion" in text


# -- Lesende Datei-Operationen (kein SecurityGate nötig) ----------------------
async def test_list_dir_lists_real_directory(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    bus = EventBus()
    engine = _engine(bus)

    text = await _run(engine, "list_dir", path=str(tmp_path))
    assert "a.txt" in text
    assert "sub/" in text


async def test_find_files_matches_glob_pattern(tmp_path):
    (tmp_path / "notes.md").write_text("x")
    (tmp_path / "readme.txt").write_text("x")
    bus = EventBus()
    engine = _engine(bus)

    text = await _run(engine, "find_files", path=str(tmp_path), pattern="*.md")
    assert "notes.md" in text
    assert "readme.txt" not in text


# -- Schreibende Datei-Operationen: SecurityGate MUSS greifen -----------------
async def test_create_file_requires_approval_and_writes_content(tmp_path):
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    target = tmp_path / "note.txt"

    text = await _run(engine, "create_file", path=str(target), content="hallo welt")

    assert target.read_text() == "hallo welt"
    assert "erstellt" in text.lower()


async def test_create_file_denied_does_not_write(tmp_path):
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)
    target = tmp_path / "note.txt"

    text = await _run(engine, "create_file", path=str(target), content="hallo welt")

    assert not target.exists()
    assert "abgelehnt" in text.lower()


async def test_delete_path_denied_leaves_file_intact(tmp_path):
    # Kern des SecurityGate: eine Ablehnung MUSS die Aktion tatsächlich
    # verhindern, sonst ist das ganze Bestätigungssystem wirkungslos.
    target = tmp_path / "wichtig.txt"
    target.write_text("nicht löschen")
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)

    text = await _run(engine, "delete_path", path=str(target))

    assert target.exists()
    assert target.read_text() == "nicht löschen"
    assert "abgelehnt" in text.lower()


async def test_delete_path_approved_removes_file(tmp_path):
    target = tmp_path / "loeschbar.txt"
    target.write_text("weg damit")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "delete_path", path=str(target))

    assert not target.exists()
    assert "Gelöscht" in text


async def test_delete_path_removes_folder_recursively(tmp_path):
    folder = tmp_path / "ordner"
    folder.mkdir()
    (folder / "innen.txt").write_text("x")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    await _run(engine, "delete_path", path=str(folder))

    assert not folder.exists()


async def test_delete_path_missing_path_reports_not_found(tmp_path):
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "delete_path", path=str(tmp_path / "gibts-nicht.txt"))
    assert "nicht gefunden" in text.lower()


async def test_move_file_moves_to_new_location(tmp_path):
    src = tmp_path / "alt.txt"
    src.write_text("inhalt")
    dst = tmp_path / "unterordner" / "neu.txt"
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    await _run(engine, "move_file", src=str(src), dst=str(dst))

    assert not src.exists()
    assert dst.read_text() == "inhalt"


async def test_create_folder_creates_nested_directories(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    await _run(engine, "create_folder", path=str(target))

    assert target.is_dir()


# -- Downloads-Übersicht (nur lesend) -----------------------------------------
async def test_downloads_lists_home_downloads_folder(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "bild.png").write_text("x")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "downloads")

    assert "bild.png" in text


# -- close_app (echtes psutil, kein Mock nötig – funktioniert plattformübergreifend)
async def test_close_app_reports_zero_for_unknown_process():
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "close_app", name="ein-prozess-der-sicher-nicht-laeuft-xyz")

    assert "Kein laufender Prozess" in text


async def test_close_app_denied_reports_rejection():
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)

    text = await _run(engine, "close_app", name="irgendwas")

    assert "abgelehnt" in text.lower()


# -- PowerShell: Plattform-Gate + gemockte Ausführung -------------------------
async def test_run_powershell_reports_unsupported_on_non_windows():
    bus = EventBus()
    engine = _engine(bus)
    assert automation_module.IS_WINDOWS is False  # Testumgebung ist Linux
    text = await _run(engine, "run_powershell", command="Get-Process")
    assert "nur unter Windows" in text


async def test_run_powershell_executes_and_returns_output_on_windows(monkeypatch):
    monkeypatch.setattr(automation_module, "IS_WINDOWS", True)

    class _FakeProcess:
        async def communicate(self):
            return b"Hallo aus PowerShell\n", b""

    async def _fake_exec(*args, **kwargs):
        assert args[0] == "powershell.exe"
        assert "Get-Process" in args
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    text = await _run(engine, "run_powershell", command="Get-Process")

    assert "Hallo aus PowerShell" in text


async def test_run_powershell_denied_never_spawns_process(monkeypatch):
    monkeypatch.setattr(automation_module, "IS_WINDOWS", True)

    async def _fake_exec(*args, **kwargs):  # pragma: no cover - darf nie laufen
        raise AssertionError("Ein abgelehnter Befehl darf nie ausgeführt werden")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)
    text = await _run(engine, "run_powershell", command="Remove-Item C:\\ -Recurse -Force")

    assert "abgelehnt" in text.lower()


# -- open_app: Plattform-Gate + gemocktes os.startfile ------------------------
async def test_open_app_reports_unsupported_on_non_windows():
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "open_app", name="notepad")
    assert "nur unter Windows" in text


async def test_open_app_calls_startfile_on_windows(monkeypatch):
    monkeypatch.setattr(automation_module, "IS_WINDOWS", True)
    calls: list[str] = []
    monkeypatch.setattr(os, "startfile", lambda name: calls.append(name), raising=False)

    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    text = await _run(engine, "open_app", name="notepad")

    assert calls == ["notepad"]
    assert "gestartet" in text.lower()
