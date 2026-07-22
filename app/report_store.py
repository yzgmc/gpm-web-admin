"""上报存储：被动接收各端 push 的 Heartbeat，按 reporter_id 索引并标记 last_seen_at。

Push 模型：web-admin 不再轮询各服务端，而是等待 server / web-server / client
主动 POST /api/v1/report 上报心跳。本模块维护内存状态表供 dashboard 读取。

判定离线：超过 STALE_SECONDS 未收到心跳即视为离线。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from gpm_common.heartbeat import Heartbeat


STALE_SECONDS = 30.0  # 超过该时长未上报视为离线


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StoredReport:
    """单条已存储的上报记录。"""

    def __init__(self, hb: Heartbeat) -> None:
        self.reporter_id = hb.reporter_id
        self.kind = hb.kind
        self.name = hb.name
        self.base_url = hb.base_url
        self.last_heartbeat = hb
        self.last_seen_at = _now()
        self.received_count = 1

    def update(self, hb: Heartbeat) -> None:
        self.last_heartbeat = hb
        self.last_seen_at = _now()
        self.received_count += 1

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        now = now or _now()
        age = (now - self.last_seen_at).total_seconds()
        return age > STALE_SECONDS

    def to_dict(self) -> dict[str, Any]:
        now = _now()
        age = (now - self.last_seen_at).total_seconds()
        online = not self.is_stale(now)
        return {
            "reporter_id": self.reporter_id,
            "kind": self.kind,
            "name": self.name,
            "base_url": self.base_url,
            "online": online,
            "status": self.last_heartbeat.status,
            "last_seen_at": self.last_seen_at.isoformat(),
            "seconds_since_seen": round(age, 1),
            "received_count": self.received_count,
            "protocol_version": self.last_heartbeat.protocol_version,
            "metrics": self.last_heartbeat.metrics,
            "extra": self.last_heartbeat.extra,
        }


class ReportStore:
    """线程安全的上报存储。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reports: dict[str, StoredReport] = {}

    def record(self, hb: Heartbeat) -> StoredReport:
        with self._lock:
            existing = self._reports.get(hb.reporter_id)
            if existing:
                existing.update(hb)
                return existing
            stored = StoredReport(hb)
            self._reports[hb.reporter_id] = stored
            return stored

    def all_reports(self) -> list[StoredReport]:
        with self._lock:
            return list(self._reports.values())

    def by_kind(self, kind: str) -> list[StoredReport]:
        with self._lock:
            return [r for r in self._reports.values() if r.kind == kind]

    def aggregate(self) -> dict[str, Any]:
        snaps = self.all_reports()
        online = [r for r in snaps if not r.is_stale()]
        # 按 kind 分组
        by_kind: dict[str, list[dict]] = {}
        for r in snaps:
            by_kind.setdefault(r.kind, []).append(r.to_dict())

        # 聚合推送条目（仅服务端上报时携带 modpacks/mods）
        games: dict[str, dict] = {}
        for r in online:
            metrics = r.last_heartbeat.metrics or {}
            for mp in metrics.get("modpacks", []) or []:
                g = mp.get("game", "unknown")
                games.setdefault(g, {"modpacks": {}, "mods": {}})
                games[g]["modpacks"][f"{mp.get('name')}@{mp.get('version')}"] = {
                    **mp,
                    "source": r.name,
                }
            for m in metrics.get("mods", []) or []:
                g = m.get("game", "unknown")
                games.setdefault(g, {"modpacks": {}, "mods": {}})
                games[g]["mods"][f"{m.get('name')}@{m.get('version')}"] = {
                    **m,
                    "source": r.name,
                }

        return {
            "generated_at": _now().isoformat(),
            "model": "push",
            "reporters_total": len(snaps),
            "reporters_online": len(online),
            "by_kind": {
                k: {
                    "total": len(v),
                    "online": sum(1 for x in v if x["online"]),
                    "items": v,
                }
                for k, v in by_kind.items()
            },
            "games": {
                g: {"modpacks": list(v["modpacks"].values()), "mods": list(v["mods"].values())}
                for g, v in games.items()
            },
        }


report_store = ReportStore()
