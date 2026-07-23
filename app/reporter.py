"""服务端上报器：构造 Heartbeat 并通过 gpm_common.Reporter 上报到 web-admin。

上报的 metrics 包含：
- modpack_count / mod_count / storage_used_bytes / uptime_seconds / error_count
- modpacks / mods：完整条目列表，供 web-admin 聚合展示推送条目
- light：状态指示灯（绿/黄/红），由 compute_server_light 根据磁盘占用与错误数计算
"""

from __future__ import annotations

import os
import uuid

from gpm_common import API_VERSION, Heartbeat, Reporter, compute_server_light

from app import storage
from app.config import settings
from app.server_info import server_info


_reporter: Reporter | None = None


def _reporter_id() -> str:
    # 优先用配置；其次用持久化 id（保证重启后仍是同一个上报端）；最后生成
    rid_file = os.path.join(settings.data_dir, ".reporter_id")
    if settings.reporter_id:
        return settings.reporter_id
    if os.path.exists(rid_file):
        try:
            with open(rid_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    rid = f"{settings.server_kind}-{uuid.uuid4().hex[:8]}"
    try:
        os.makedirs(settings.data_dir, exist_ok=True)
        with open(rid_file, "w", encoding="utf-8") as f:
            f.write(rid)
    except OSError:
        pass
    return rid


def _build_heartbeat() -> Heartbeat:
    modpacks = storage.list_modpacks()
    mods = storage.list_mods()
    # 计算状态指示灯：基于存储目录磁盘占用 + 累计错误数
    light = compute_server_light(settings.data_dir, error_count=server_info.error_count)
    return Heartbeat(
        reporter_id=_reporter_id(),
        kind=settings.server_kind,
        name=settings.server_name,
        base_url=settings.public_base_url,
        status="online",
        protocol_version=API_VERSION,
        light=light,
        metrics={
            "modpack_count": len(modpacks),
            "mod_count": len(mods),
            "storage_used_bytes": storage.storage_used_bytes(),
            "uptime_seconds": server_info.uptime_seconds(),
            "error_count": server_info.error_count,
            # 携带完整条目，供 web-admin 聚合推送条目视图
            "modpacks": [m.model_dump(mode="json") for m in modpacks],
            "mods": [m.model_dump(mode="json") for m in mods],
            # 携带管理员账号（用户名+hash），供 web-admin 同步登录用户
            "admin_users": settings.admin_users(),
            # 灯色冗余放进 metrics，便于后台前端直接读取
            "light_level": light.level,
            "light_reason": light.reason,
        },
    )


def start_reporter() -> None:
    """启动上报线程。若未配置 GPM_ADMIN_URL 则跳过。"""
    global _reporter
    if not settings.admin_url:
        return
    if _reporter is not None:
        return
    _reporter = Reporter(
        admin_url=settings.admin_url,
        build_payload=_build_heartbeat,
        interval=settings.reporter_interval,
    )
    _reporter.start()


def stop_reporter() -> None:
    global _reporter
    if _reporter is not None:
        _reporter.stop()
        _reporter = None


def restart_reporter() -> None:
    """根据当前 settings 重启上报线程。配置变更后调用以热生效。"""
    global _reporter
    stop_reporter()
    start_reporter()
