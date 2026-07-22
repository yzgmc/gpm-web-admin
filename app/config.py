"""网页后台配置。

Push 模型下不再配置受监测服务端地址——各端会主动向本服务上报，web-admin 只需暴露
/api/v1/report。登录认证保护仪表盘 API；/api/v1/report 对各上报端保持开放。
"""

from __future__ import annotations

import os

from gpm_common import generate_secret, hash_password


class Settings:
    host: str = os.getenv("GPM_HOST", "0.0.0.0")
    port: int = int(os.getenv("GPM_PORT", "8080"))
    # 用于告知上报端"过期阈值"，仅供参考展示
    stale_seconds: float = float(os.getenv("GPM_STALE_SECONDS", "30"))

    # 登录认证
    _auth_secret_env: str = os.getenv("GPM_AUTH_SECRET", "")  # 留空则进程内随机生成
    _users_env: str = os.getenv("GPM_USERS", "")  # user1:hash1,user2:hash2；留空用默认 admin/admin123

    def __init__(self) -> None:
        # 兜底 secret：未配置则进程内随机生成（重启后所有 token 失效，仅适合开发）
        self._secret = self._auth_secret_env or generate_secret()
        self._users = self._parse_users(self._users_env)

    @staticmethod
    def _parse_users(raw: str) -> dict[str, str]:
        if raw:
            users: dict[str, str] = {}
            for pair in raw.split(","):
                pair = pair.strip()
                if ":" in pair:
                    u, h = pair.split(":", 1)
                    users[u.strip()] = h.strip()
            return users
        # 默认管理员：admin / admin123
        return {"admin": hash_password("admin123")}

    @property
    def auth_secret(self) -> str:
        return self._secret

    @property
    def users(self) -> dict[str, str]:
        return self._users


settings = Settings()
