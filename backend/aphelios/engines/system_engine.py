"""SystemEngine – echte System-Telemetrie via ``psutil``.

Sammelt CPU/RAM/Disk/Netzwerk/Temperatur/Akku und optional GPU/VRAM und
publiziert periodisch ``system.stats``. Läuft plattformübergreifend; Werte,
die auf der aktuellen Plattform nicht verfügbar sind, werden als ``None``
gemeldet (im HUD als ``n/a`` dargestellt).
"""

from __future__ import annotations

import asyncio
import time

import psutil

from aphelios.core.engine import BaseEngine

# --- Optionale GPU-Telemetrie (NVIDIA) -------------------------------------
try:  # pragma: no cover – hardwareabhängig
    import pynvml

    pynvml.nvmlInit()
    _NVML = True
except Exception:  # noqa: BLE001 – jede Art von Fehlen ist ok
    _NVML = False


class SystemEngine(BaseEngine):
    """Publiziert regelmäßig System-Statistiken auf dem Bus."""

    name = "system"

    async def start(self) -> None:
        self._running = True
        # Erster psutil.cpu_percent-Aufruf initialisiert nur den Zähler.
        psutil.cpu_percent(interval=None)
        self._last_net = psutil.net_io_counters()
        self._last_net_ts = time.time()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        task = getattr(self, "_task", None)
        if task:
            task.cancel()

    async def _loop(self) -> None:
        interval = self.config.stats_interval
        while self._running:
            try:
                await self.emit("system.stats", self.collect())
            except Exception:  # noqa: BLE001
                self.log.exception("failed to collect system stats")
            await asyncio.sleep(interval)

    # -- Erhebung -------------------------------------------------------------
    def collect(self) -> dict:
        """Erfasst einen vollständigen Telemetrie-Schnappschuss."""
        return {
            "cpu": self._cpu(),
            "ram": self._ram(),
            "disk": self._disk(),
            "gpu": self._gpu(),
            "vram": self._vram(),
            "network": self._network(),
            "temperature": self._temperature(),
            "battery": self._battery(),
            "timestamp": time.time(),
        }

    def _cpu(self) -> dict:
        return {
            "percent": psutil.cpu_percent(interval=None),
            "cores": psutil.cpu_count(logical=True),
        }

    def _ram(self) -> dict:
        vm = psutil.virtual_memory()
        return {
            "percent": vm.percent,
            "used_gb": round(vm.used / 1e9, 2),
            "total_gb": round(vm.total / 1e9, 2),
        }

    def _disk(self) -> dict:
        du = psutil.disk_usage("/")
        return {
            "percent": du.percent,
            "used_gb": round(du.used / 1e9, 2),
            "total_gb": round(du.total / 1e9, 2),
        }

    def _network(self) -> dict:
        now = time.time()
        counters = psutil.net_io_counters()
        elapsed = max(now - self._last_net_ts, 1e-6)
        up = (counters.bytes_sent - self._last_net.bytes_sent) / elapsed
        down = (counters.bytes_recv - self._last_net.bytes_recv) / elapsed
        self._last_net = counters
        self._last_net_ts = now
        return {
            "up_kbps": round(up / 1024, 1),
            "down_kbps": round(down / 1024, 1),
        }

    def _temperature(self) -> float | None:
        getter = getattr(psutil, "sensors_temperatures", None)
        if not getter:
            return None
        try:
            temps = getter()
        except Exception:  # noqa: BLE001
            return None
        for entries in temps.values():
            for entry in entries:
                if entry.current:
                    return round(entry.current, 1)
        return None

    def _battery(self) -> dict | None:
        getter = getattr(psutil, "sensors_battery", None)
        if not getter:
            return None
        try:
            batt = getter()
        except Exception:  # noqa: BLE001
            return None
        if batt is None:
            return None
        return {
            "percent": round(batt.percent, 1),
            "plugged": batt.power_plugged,
        }

    def _gpu(self) -> dict | None:
        if not _NVML:  # pragma: no cover
            return None
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            return {"percent": util.gpu}
        except Exception:  # noqa: BLE001
            return None

    def _vram(self) -> dict | None:
        if not _NVML:  # pragma: no cover
            return None
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return {
                "percent": round(mem.used / mem.total * 100, 1),
                "used_gb": round(mem.used / 1e9, 2),
                "total_gb": round(mem.total / 1e9, 2),
            }
        except Exception:  # noqa: BLE001
            return None
