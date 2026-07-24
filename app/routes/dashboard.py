"""仪表盘 API：从 report_store 读取各端上报状态，聚合为仪表盘数据。

访问需登录（携带 Authorization: Bearer <token>）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from gpm_common import require_admin

from app.config import settings
from app.report_store import report_store


router = APIRouter(prefix="/api/v1")

# 仪表盘数据为后台管理视图，仅管理员可访问
_require_admin = Depends(require_admin(settings.auth_secret))


@router.get("/dashboard", dependencies=[_require_admin])
def dashboard():
    """返回完整仪表盘数据：所有上报端状态 + 推送条目聚合。"""
    return report_store.aggregate()
