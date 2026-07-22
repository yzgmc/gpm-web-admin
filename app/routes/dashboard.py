"""仪表盘 API：从 report_store 读取各端上报状态，聚合为仪表盘数据。"""

from __future__ import annotations

from fastapi import APIRouter

from app.report_store import report_store


router = APIRouter(prefix="/api/v1")


@router.get("/dashboard")
def dashboard():
    """返回完整仪表盘数据：所有上报端状态 + 推送条目聚合。"""
    return report_store.aggregate()
