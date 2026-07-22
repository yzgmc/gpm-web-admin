"""网页后台配置：仅监听端口。Push 模型下不再配置受监测服务端地址——
各端会主动向本服务上报，web-admin 只需暴露 /api/v1/report。
"""

from __future__ import annotations

import os


class Settings:
    host: str = os.getenv("GPM_HOST", "0.0.0.0")
    port: int = int(os.getenv("GPM_PORT", "8080"))
    # 用于告知上报端"过期阈值"，仅供参考展示
    stale_seconds: float = float(os.getenv("GPM_STALE_SECONDS", "30"))


settings = Settings()
