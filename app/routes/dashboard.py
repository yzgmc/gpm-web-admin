"""仪表盘 API：从 report_store 读取各端上报状态，聚合为仪表盘数据。

访问需登录（携带 Authorization: Bearer <token>）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from gpm_common import require_token

from app.config import settings
from app.report_store import report_store


router = APIRouter(prefix="/api/v1")

# 仪表盘数据需要登录后访问
_require_auth = Depends(require_token(settings.auth_secret))


@router.get("/dashboard", dependencies=[_require_auth])
def dashboard():
    """返回完整仪表盘数据：所有上报端状态 + 推送条目聚合。"""
    return report_store.aggregate()
