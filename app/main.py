"""FastAPI 应用入口：托管仪表盘 API 与静态前端。

Push 模型：web-admin 不再主动轮询各服务端，而是被动接收 server / web-server / client
通过 POST /api/v1/report 上报的 Heartbeat。仪表盘从内存 report_store 读取数据。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes import dashboard, report


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Game Push Manager - Web Admin",
        description="被动接收各端上报的 Heartbeat，监测 windows-server / web-server / client 状态及推送条目。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(report.router)
    app.include_router(dashboard.router)

    # 静态资源
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app


app = create_app()
