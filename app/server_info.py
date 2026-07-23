"""服务端运行时信息跟踪：启动时间、累计请求数等，供 status 接口使用。"""

from __future__ import annotations

import time
from datetime import datetime, timezone


class ServerInfo:
    def __init__(self) -> None:
        self.started_at = datetime.now(timezone.utc)
        self._start_ts = time.time()
        self.request_count = 0
        self.upload_count = 0
        self.download_count = 0
        self.error_count = 0

    def uptime_seconds(self) -> float:
        return time.time() - self._start_ts

    def record_request(self) -> None:
        self.request_count += 1

    def record_upload(self) -> None:
        self.upload_count += 1

    def record_download(self) -> None:
        self.download_count += 1

    def record_error(self) -> None:
        self.error_count += 1


server_info = ServerInfo()
