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

from gpm_common import LightLevel, aggregate_light
from gpm_common.heartbeat import Heartbeat

from app.config import settings


STALE_SECONDS = 30.0  # 兜底默认；运行时用 settings.stale_seconds


def _stale_threshold() -> float:
    try:
        from app.config import settings
        return settings.stale_seconds
    except Exception:
        return STALE_SECONDS


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
        return age > _stale_threshold()

    def light_level(self) -> str:
        """返回该上报端的灯色。离线视为红灯；未上报灯色视为 off。"""
        if self.is_stale():
            return LightLevel.RED
        hb_light = self.last_heartbeat.light
        if hb_light is None:
            return LightLevel.OFF
        return hb_light.level

    def to_dict(self) -> dict[str, Any]:
        now = _now()
        age = (now - self.last_seen_at).total_seconds()
        online = not self.is_stale(now)
        # 灯色：离线 -> red；否则用上报的 light（无则 off）
        level = self.light_level()
        reason = ""
        if online and self.last_heartbeat.light is not None:
            reason = self.last_heartbeat.light.reason
        elif not online:
            reason = f"超过 {int(_stale_threshold())}s 未上报心跳"
        return {
            "reporter_id": self.reporter_id,
            "kind": self.kind,
            "name": self.name,
            "base_url": self.base_url,
            "online": online,
            "status": self.last_heartbeat.status,
            "light": {"level": level, "reason": reason},
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
            else:
                existing = StoredReport(hb)
                self._reports[hb.reporter_id] = stored = existing
        # 在锁外同步管理员账号到本地用户表（避免死锁）
        admin_users = (hb.metrics or {}).get("admin_users")
        if admin_users:
            try:
                settings.sync_admin_users(admin_users, source=hb.reporter_id)
            except Exception:
                pass
        return existing

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

        # 总体系统灯：所有上报端灯色取最严重者；无上报端则 off
        all_levels = [r.light_level() for r in snaps]
        overall_light = aggregate_light(all_levels) if all_levels else LightLevel.OFF

        # 按 kind 聚合灯色
        kind_lights: dict[str, str] = {}
        for kind, items in by_kind.items():
            levels = [it["light"]["level"] for it in items]
            kind_lights[kind] = aggregate_light(levels) if levels else LightLevel.OFF

        return {
            "generated_at": _now().isoformat(),
            "model": "push",
            "reporters_total": len(snaps),
            "reporters_online": len(online),
            "overall_light": overall_light,
            "kind_lights": kind_lights,
            "by_kind": {
                k: {
                    "total": len(v),
                    "online": sum(1 for x in v if x["online"]),
                    "light": kind_lights.get(k, LightLevel.OFF),
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
