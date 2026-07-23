"""网页后台配置。

Push 模型下不再配置受监测服务端地址——各端会主动向本服务上报，web-admin 只需暴露
/api/v1/report。登录认证保护仪表盘 API；/api/v1/report 对各上报端保持开放。

用户同步：各服务端上报心跳时携带 admin_users（管理员账号 + hash），
web-admin 收到后合并到本地用户表并持久化，实现「服务端管理员可登录后台」。
"""

from __future__ import annotations

import json
import os
import threading

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
        self._secret = self._auth_secret_env or generate_secret()
        self._lock = threading.Lock()
        self._data_dir = os.getenv("GPM_DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/data")
        self._users_file = os.path.join(self._data_dir, "users.json")
        self._users = self._load_users()

    # ---------- 用户持久化 ----------
    # 存储格式: {username: {"hash": "<pbkdf2_hash>", "role": "admin"|"user"}}
    def _load_users(self) -> dict[str, dict]:
        """优先读 users.json；不存在则用默认 admin/admin123 并写入文件。"""
        if self._users_env:
            return self._parse_users_env(self._users_env)
        if os.path.exists(self._users_file):
            try:
                with open(self._users_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if raw:
                    # 兼容旧格式（value 为纯 hash 字符串）
                    users = {}
                    for k, v in raw.items():
                        if isinstance(v, str):
                            users[k] = {"hash": v, "role": "admin"}
                        else:
                            users[k] = v
                    return users
            except (OSError, json.JSONDecodeError):
                pass
        # 默认管理员：admin / admin123
        default = {"admin": {"hash": hash_password("admin123"), "role": "admin"}}
        self._save_users(default)
        return default

    def _save_users(self, users: dict[str, dict]) -> None:
        try:
            os.makedirs(self._data_dir, exist_ok=True)
            with open(self._users_file, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _parse_users_env(raw: str) -> dict[str, dict]:
        users: dict[str, dict] = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if ":" in pair:
                parts = pair.split(":")
                u = parts[0].strip()
                h = parts[1].strip()
                role = parts[2].strip() if len(parts) > 2 else "admin"
                users[u] = {"hash": h, "role": role}
        return users

    # ---------- 用户访问 API ----------
    @property
    def users(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._users.items()}

    @property
    def auth_secret(self) -> str:
        return self._secret

    def user_hash(self, username: str) -> str | None:
        with self._lock:
            entry = self._users.get(username)
            return entry["hash"] if entry else None

    def user_role(self, username: str) -> str | None:
        with self._lock:
            entry = self._users.get(username)
            return entry["role"] if entry else None

    def sync_admin_users(self, admin_users: list[dict], source: str = "") -> int:
        """合并服务端上报的管理员账号到本地用户表。
        admin_users: [{"username": ..., "hash": ...}, ...]
        source: 上报来源（reporter_id），用于追踪同步来源。
        已存在的本地用户只更新 hash；新用户标记 _source=source。
        当某个 source 不再上报某用户时（降级/删除），该用户会被清除。
        """
        with self._lock:
            # 先清除该 source 之前同步过来的用户（本地用户不受影响）
            if source:
                to_remove = [u for u, d in self._users.items() if d.get("_source") == source]
                for u in to_remove:
                    del self._users[u]
            # 再添加本次上报的管理员
            changed = False
            for u in admin_users:
                uname = u.get("username", "")
                uhash = u.get("hash", "")
                if not uname or not uhash:
                    continue
                existing = self._users.get(uname)
                if existing and not existing.get("_source"):
                    # 本地用户：只更新 hash，保持 local 身份不被清除
                    if existing["hash"] != uhash:
                        existing["hash"] = uhash
                        changed = True
                else:
                    # 新用户或之前同步过的：标记来源
                    self._users[uname] = {"hash": uhash, "role": "admin", "_source": source}
                    changed = True
            if changed:
                self._save_users(self._users)
            return sum(1 for d in self._users.values() if d.get("role") == "admin")


settings = Settings()
