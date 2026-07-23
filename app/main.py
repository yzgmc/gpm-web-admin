"""FastAPI 应用入口：融合体 = 网页后台 + 网页服务端。

合并后单进程同时提供：
1. 网页后台（接收各端 POST /api/v1/report，展示仪表盘）
2. 网页服务端（上传/管理整合包模组、向客户端提供同步下载 API、用户管理、配置管理）

自上报：启动后默认把 admin_url 指向自己（http://127.0.0.1:{port}），
后台自动把自己作为一个上报端纳入仪表盘，无需手动配置。
"""

from __future__ import annotations

# 导入 gpm_common 即触发内置适配器注册（minecraft 等）
import gpm_common  # noqa: F401
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request as Req
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from gpm_common import API_VERSION, AuthError, GamePushError

from app.config import settings
from app.reporter import start_reporter, stop_reporter
from app.routes import auth, config, dashboard, games, mods, modpacks, report, status, sync, update
from app.server_info import server_info
from app.updater import start_updater, stop_updater


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Game Push Manager - 融合体",
        version=API_VERSION,
        description="网页后台 + 网页服务端融合：既接收上报展示仪表盘，又提供上传/同步/管理 API，并自动上报自身。",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _count_requests(request: Request, call_next):
        server_info.record_request()
        return await call_next(request)

    @app.exception_handler(GamePushError)
    async def _handle_push_error(_: Request, exc: GamePushError):
        server_info.record_error()
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(AuthError)
    async def _handle_auth_error(_: Req, exc: AuthError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": "UNAUTHORIZED"},
        )

    # ---------- 后台路由 ----------
    app.include_router(report.router)       # POST /api/v1/report（接收上报，无鉴权）
    app.include_router(dashboard.router)    # GET /api/v1/dashboard（仪表盘，需登录）

    # ---------- 服务端路由 ----------
    app.include_router(auth.router)         # 登录/改密/用户管理
    app.include_router(config.router)       # 运行时配置（admin_url 等）
    app.include_router(games.router)        # 游戏列表
    app.include_router(status.router)       # 服务端状态
    app.include_router(sync.router)         # 客户端同步/下载
    app.include_router(modpacks.router)     # 整合包 CRUD
    app.include_router(mods.router)         # 模组 CRUD
    app.include_router(update.router)       # 自动更新管理

    # 静态资源
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.on_event("startup")
    def _start_reporter():
        # 启动自上报线程：默认 admin_url 指向自己，后台自动纳入本服务
        start_reporter()
        # 启动自动更新检查线程（每5分钟检查 GitHub 仓库更新）
        start_updater()

    @app.on_event("shutdown")
    def _stop_reporter():
        stop_reporter()
        stop_updater()

    @app.get("/")
    def root():
        # 根路径：默认进仪表盘（JS 会在无 token 时跳转到 /login）
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/login")
    def login_page():
        return FileResponse(str(STATIC_DIR / "login.html"))

    @app.get("/admin")
    def admin_page():
        # 服务端管理 UI（整合包/模组/用户/配置）
        return FileResponse(str(STATIC_DIR / "admin.html"))

    @app.get("/api/info")
    def api_info():
        return {
            "service": "gpm-web-admin-fusion",
            "kind": settings.server_kind,
            "protocol_version": API_VERSION,
            "docs": "/docs",
            "admin_ui": "/admin",
            "dashboard": "/",
            "reporting_to": settings.admin_url or None,
            "server_name": settings.server_name,
        }

    return app


app = create_app()
