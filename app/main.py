"""FastAPI 应用入口：托管仪表盘 API 与静态前端。

Push 模型：web-admin 不再主动轮询各服务端，而是被动接收 server / web-server / client
通过 POST /api/v1/report 上报的 Heartbeat。仪表盘从内存 report_store 读取数据。

登录认证：仪表盘 API（GET /api/v1/dashboard）需要 token；上报接收（POST /api/v1/report）
对各上报端保持开放；静态页面（/ 与 /login）可直接访问，由前端 JS 处理登录跳转。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from gpm_common import AuthError

from app.routes import auth, dashboard, report


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

    @app.exception_handler(AuthError)
    async def _handle_auth_error(_: Request, exc: AuthError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": "UNAUTHORIZED"},
        )

    # /api/v1/report 对各上报端开放（无 token）；/api/v1/dashboard 需登录
    app.include_router(report.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)

    # 静态资源
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        # 仪表盘页：JS 会在无 token 时跳转到 /login
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/login")
    def login_page():
        return FileResponse(str(STATIC_DIR / "login.html"))

    return app


app = create_app()
