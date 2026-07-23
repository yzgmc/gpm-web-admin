"""更新管理路由：查询状态 / 手动检查 / 手动应用更新。

所有操作都需要管理员 token。自动检查由后台线程每5分钟执行一次。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from gpm_common import require_token, route

from app.config import settings
from app.updater import apply_update, check_for_updates, status

router = APIRouter()
_require_auth = Depends(require_token(settings.auth_secret))


@router.get(route("/update/status"), dependencies=[_require_auth])
def get_update_status():
    """查询当前更新状态（上次检查时间、是否有更新、自动更新开关等）。"""
    return status.snapshot()


@router.post(route("/update/check"), dependencies=[_require_auth])
def manual_check():
    """手动检查是否有更新（不应用，仅 fetch + 比较 SHA）。"""
    result = check_for_updates()
    status.set(
        last_check=__import__("time").time(),
        last_result="update_available" if result["has_update"] else "up_to_date",
        last_message=result["message"],
        local_sha=result["local_sha"],
        remote_sha=result["remote_sha"],
    )
    return result


@router.post(route("/update/apply"), dependencies=[_require_auth])
def manual_apply():
    """手动应用更新：git pull + pip install + 重启服务。

    成功后进程会退出，systemd 自动重启。响应在退出前返回。
    """
    return apply_update()


@router.patch(route("/update/auto"), dependencies=[_require_auth])
def toggle_auto_update(body: dict):
    """开启/关闭自动更新检查。body: {"enabled": true|false}"""
    enabled = bool(body.get("enabled", True))
    status.set(auto_enabled=enabled, last_message=f"自动更新已{'开启' if enabled else '关闭'}")
    return {"auto_enabled": enabled}
