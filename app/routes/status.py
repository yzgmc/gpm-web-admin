"""服务端状态路由，供 web-admin 监测。"""

from __future__ import annotations

from fastapi import APIRouter

from gpm_common import API_VERSION, StatusResponse, route

from app import storage
from app.config import settings
from app.server_info import server_info


router = APIRouter()


@router.get(route("/status"))
def get_status():
    return StatusResponse(
        server_name=settings.server_name,
        server_kind=settings.server_kind,
        status="online",
        protocol_version=API_VERSION,
        uptime_seconds=server_info.uptime_seconds(),
        modpack_count=len(storage.list_modpacks()),
        mod_count=len(storage.list_mods()),
        storage_used_bytes=storage.storage_used_bytes(),
        started_at=server_info.started_at,
    ).model_dump()
