"""FastAPI 应用入口：托管仪表盘 API 与静态前端。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.monitor import monitor
from app.routes import dashboard


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Game Push Manager - Web Admin",
        description="监测 windows-server 与 web-server 状态及游戏推送条目。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(dashboard.router)

    @app.on_event("startup")
    def _start_monitor():
        monitor.start()

    @app.on_event("shutdown")
    def _stop_monitor():
        monitor.stop()

    # 静态资源
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app


app = create_app()
