"""监测逻辑：周期性轮询受监测服务端的 status / sync 接口并缓存结果。

设计为单进程内存缓存，足够网页后台使用。如需多副本部署可后续替换为 Redis。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import MonitoredServer, settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ServerSnapshot:
    """单个服务端的一次快照。"""

    def __init__(self, server: MonitoredServer) -> None:
        self.server = server
        self.online: bool = False
        self.status: Optional[dict] = None
        self.sync: Optional[dict] = None
        self.last_checked_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.latency_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "name": self.server.name,
            "kind": self.server.kind,
            "base_url": self.server.base_url,
            "online": self.online,
            "latency_ms": self.latency_ms,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "last_error": self.last_error,
            "status": self.status,
            "sync": self.sync,
        }


class Monitor:
    """监测器：后台线程周期性刷新所有服务端快照。"""

    def __init__(self) -> None:
        self._snapshots: dict[str, ServerSnapshot] = {
            s.base_url: ServerSnapshot(s) for s in settings.servers
        }
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gpm-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.refresh_once()
            self._stop.wait(settings.monitor_interval)

    def refresh_once(self) -> None:
        for snapshot in list(self._snapshots.values()):
            self._poll_one(snapshot)

    def _poll_one(self, snapshot: ServerSnapshot) -> None:
        base = snapshot.server.base_url
        snapshot.last_checked_at = _now()
        snapshot.last_error = None
        try:
            start = time.time()
            with httpx.Client(timeout=settings.request_timeout) as client:
                status_resp = client.get(f"{base}/api/v1/status")
                status_resp.raise_for_status()
                snapshot.status = status_resp.json()
                snapshot.online = True

                sync_resp = client.get(f"{base}/api/v1/sync")
                sync_resp.raise_for_status()
                snapshot.sync = sync_resp.json()

            snapshot.latency_ms = round((time.time() - start) * 1000, 1)
        except Exception as exc:  # noqa: BLE001
            snapshot.online = False
            snapshot.last_error = f"{type(exc).__name__}: {exc}"
            snapshot.latency_ms = None

    def all_snapshots(self) -> list[ServerSnapshot]:
        with self._lock:
            return list(self._snapshots.values())

    def aggregate(self) -> dict[str, Any]:
        """聚合所有快照为仪表盘数据。"""
        snaps = self.all_snapshots()
        total_modpacks = sum(
            (s.status or {}).get("modpack_count", 0) for s in snaps if s.online
        )
        total_mods = sum(
            (s.status or {}).get("mod_count", 0) for s in snaps if s.online
        )
        online_count = sum(1 for s in snaps if s.online)
        # 聚合推送条目（按 game 分组，按 name+version 去重）
        games: dict[str, dict] = {}
        for s in snaps:
            if not s.online or not s.sync:
                continue
            for mp in s.sync.get("modpacks", []):
                key = (mp.get("game"), mp.get("name"), mp.get("version"))
                games.setdefault(mp.get("game", "unknown"), {"modpacks": {}, "mods": {}})
                games[mp["game"]]["modpacks"][f"{key[1]}@{key[2]}"] = {
                    **mp,
                    "source": s.server.kind,
                }
            for m in s.sync.get("mods", []):
                games.setdefault(m.get("game", "unknown"), {"modpacks": {}, "mods": {}})
                mk = f"{m.get('name')}@{m.get('version')}"
                games[m["game"]]["mods"][mk] = {**m, "source": s.server.kind}
        return {
            "generated_at": _now().isoformat(),
            "servers_online": online_count,
            "servers_total": len(snaps),
            "total_modpacks": total_modpacks,
            "total_mods": total_mods,
            "servers": [s.to_dict() for s in snaps],
            "games": {
                g: {"modpacks": list(v["modpacks"].values()), "mods": list(v["mods"].values())}
                for g, v in games.items()
            },
        }


monitor = Monitor()
