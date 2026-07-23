"""运行时配置路由：查看 / 修改后台地址等可热更新配置。写操作需 token。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gpm_common import require_token, route

from app.config import settings
from app.reporter import restart_reporter


router = APIRouter()
_require_auth = Depends(require_token(settings.auth_secret))


class RuntimeConfig(BaseModel):
    admin_url: str
    server_name: str
    public_base_url: str
    reporter_interval: float


class RuntimeConfigUpdate(BaseModel):
    admin_url: str | None = None
    server_name: str | None = None
    public_base_url: str | None = None
    reporter_interval: float | None = None


@router.get(route("/config"), response_model=RuntimeConfig)
def get_config() -> RuntimeConfig:
    """读取当前运行时配置。"""
    return RuntimeConfig(
        admin_url=settings.admin_url,
        server_name=settings.server_name,
        public_base_url=settings.public_base_url,
        reporter_interval=settings.reporter_interval,
    )


@router.put(route("/config"), response_model=RuntimeConfig, dependencies=[_require_auth])
def update_config(req: RuntimeConfigUpdate) -> RuntimeConfig:
    """修改运行时配置并热重启上报线程。

    主要用于在 UI 里修改「后台地址」（admin_url），修改后立即生效，无需重启服务。
    """
    updated = settings.update_runtime(
        admin_url=req.admin_url,
        server_name=req.server_name,
        public_base_url=req.public_base_url,
        reporter_interval=req.reporter_interval,
    )
    # 配置变更后重启上报线程以热生效
    restart_reporter()
    return RuntimeConfig(**updated)
