"""仪表盘 API：返回聚合后的监测数据，前端据此渲染。"""

from __future__ import annotations

from fastapi import APIRouter

from app.monitor import monitor


router = APIRouter(prefix="/api/v1")


@router.get("/dashboard")
def dashboard():
    """返回完整仪表盘数据：服务端状态 + 推送条目聚合。"""
    return monitor.aggregate()


@router.get("/dashboard/refresh")
def refresh():
    """触发一次同步刷新并返回最新数据。"""
    monitor.refresh_once()
    return monitor.aggregate()
