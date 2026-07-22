"""上报接收路由：各端 POST /api/v1/report 主动上报 Heartbeat。"""

from __future__ import annotations

from fastapi import APIRouter

from gpm_common import Heartbeat

from app.report_store import report_store


router = APIRouter(prefix="/api/v1")


@router.post("/report")
def report(hb: Heartbeat):
    """接收一个端的心跳上报，存入内存并返回 ack。"""
    stored = report_store.record(hb)
    return {
        "ok": True,
        "reporter_id": stored.reporter_id,
        "received_count": stored.received_count,
    }
