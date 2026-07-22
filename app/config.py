"""网页后台配置：监测目标地址、轮询参数。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class MonitoredServer:
    """受监测的单个服务端。"""

    name: str            # 展示名，由 status 接口返回，初始用配置名
    kind: str            # windows-server / web-server
    base_url: str        # 形如 http://127.0.0.1:8000


@dataclass
class Settings:
    host: str = os.getenv("GPM_HOST", "0.0.0.0")
    port: int = int(os.getenv("GPM_PORT", "8080"))
    monitor_interval: float = float(os.getenv("GPM_MONITOR_INTERVAL", "10"))
    request_timeout: float = float(os.getenv("GPM_REQUEST_TIMEOUT", "5"))
    servers: list[MonitoredServer] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.servers:
            self.servers = [
                MonitoredServer(
                    name="Windows Server",
                    kind="windows-server",
                    base_url=os.getenv(
                        "GPM_WINDOWS_SERVER_URL", "http://127.0.0.1:8000"
                    ).rstrip("/"),
                ),
                MonitoredServer(
                    name="Web Server",
                    kind="web-server",
                    base_url=os.getenv(
                        "GPM_WEB_SERVER_URL", "http://127.0.0.1:8001"
                    ).rstrip("/"),
                ),
            ]


settings = Settings()
