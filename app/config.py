"""融合体配置：既是网页后台（接收上报），又是网页服务端（上传/同步）。

合并要点：
- 继承 web-server 的运行时配置（admin_url / server_name / public_base_url / reporter_interval）
- 继承 web-admin 的用户同步功能（接收其他服务端上报的管理员账号）
- admin_url 默认指向自己（http://127.0.0.1:{port}），启动后自动上报给自己，
  实现"后台自动配置当前运行的服务端"。

用户同步：其他服务端上报心跳时携带 admin_users，本服务合并到本地用户表并持久化。
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from gpm_common import generate_secret, hash_password

# Nuitka 编译后存在该变量；用于区分打包 exe 与源码运行环境
_IS_COMPILED = "__compiled__" in dir()


def _default_data_dir() -> str:
    """数据目录：Nuitka 打包后用 exe 同级 data；源码运行用仓库根 data。"""
    if _IS_COMPILED:
        return str(Path(sys.executable).resolve().parent / "data")
    return str(Path(__file__).resolve().parent.parent / "data")


class Settings:
    host: str = os.getenv("GPM_HOST", "0.0.0.0")
    port: int = int(os.getenv("GPM_PORT", "8001"))
    data_dir: str = os.getenv("GPM_DATA_DIR", _default_data_dir())
    server_kind: str = "web-server"  # 融合体对外的 kind
    max_upload_mb: int = int(os.getenv("GPM_MAX_UPLOAD_MB", "4096"))
    reporter_id: str = os.getenv("GPM_REPORTER_ID", "")  # 留空则用 server_name
    # 后台离线判定阈值（继承自 web-admin）
    stale_seconds: float = float(os.getenv("GPM_STALE_SECONDS", "30"))

    def __init__(self) -> None:
        # 兜底 secret：未配置则进程内随机生成（重启后所有 token 失效，仅适合开发）
        self._secret = os.getenv("GPM_AUTH_SECRET", "") or generate_secret()
        self._lock = threading.Lock()
        self._users_file = os.path.join(self.data_dir, "users.json")
        self._users = self._load_users()
        # 运行时可改的配置：从 server.json 读，环境变量优先级最高
        self._config_file = os.path.join(self.data_dir, "server.json")
        self._runtime = self._load_runtime_config()

    # ---------- 运行时配置持久化 ----------
    def _load_runtime_config(self) -> dict:
        """加载可热更新的配置。
        优先级：环境变量 > server.json > 类默认值。
        关键：admin_url 默认指向自己，启动即自动上报给自己。"""
        saved: dict = {}
        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
            except (OSError, json.JSONDecodeError):
                saved = {}
        # admin_url 默认指向自己，实现"后台自动配置当前服务端"
        self_url = f"http://127.0.0.1:{self.port}"
        return {
            "admin_url": os.getenv("GPM_ADMIN_URL", "") or saved.get("admin_url", self_url),
            "server_name": os.getenv("GPM_SERVER_NAME") or saved.get("server_name", "gpm-web-admin"),
            "public_base_url": os.getenv("GPM_PUBLIC_BASE_URL") or saved.get("public_base_url", self_url),
            "reporter_interval": float(os.getenv("GPM_REPORTER_INTERVAL") or saved.get("reporter_interval", 10.0)),
        }

    def _save_runtime_config(self) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._runtime, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @property
    def admin_url(self) -> str:
        return self._runtime["admin_url"]

    @property
    def server_name(self) -> str:
        return self._runtime["server_name"]

    @property
    def public_base_url(self) -> str:
        return self._runtime["public_base_url"]

    @property
    def reporter_interval(self) -> float:
        return self._runtime["reporter_interval"]

    def update_runtime(self, *, admin_url: str | None = None,
                       server_name: str | None = None,
                       public_base_url: str | None = None,
                       reporter_interval: float | None = None) -> dict:
        """更新运行时配置并持久化。返回更新后的完整配置。"""
        with self._lock:
            if admin_url is not None:
                self._runtime["admin_url"] = admin_url.strip()
            if server_name is not None and server_name.strip():
                self._runtime["server_name"] = server_name.strip()
            if public_base_url is not None:
                self._runtime["public_base_url"] = public_base_url.strip()
            if reporter_interval is not None and reporter_interval > 0:
                self._runtime["reporter_interval"] = float(reporter_interval)
            self._save_runtime_config()
            return dict(self._runtime)

    # ---------- 用户持久化 ----------
    # 存储格式: {username: {"hash": "<pbkdf2_hash>", "role": "admin"|"user", "_source"?: ...}}
    def _load_users(self) -> dict[str, dict]:
        """优先读 users.json；不存在则用默认 admin/admin123 并写入文件。
        兼容旧格式（value 为纯 hash 字符串）自动迁移。"""
        if os.getenv("GPM_USERS"):
            return self._parse_users_env(os.getenv("GPM_USERS", ""))
        if os.path.exists(self._users_file):
            try:
                with open(self._users_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if raw:
                    users = {}
                    for k, v in raw.items():
                        if isinstance(v, str):
                            users[k] = {"hash": v, "role": "admin" if k == "admin" else "user"}
                        else:
                            users[k] = v
                    return users
            except (OSError, json.JSONDecodeError):
                pass
        default = {"admin": {"hash": hash_password("admin123"), "role": "admin"}}
        self._save_users(default)
        return default

    def _save_users(self, users: dict[str, dict]) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
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
                role = parts[2].strip() if len(parts) > 2 else "user"
                users[u] = {"hash": h, "role": role}
        return users

    # ---------- 用户管理 API ----------
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

    def admin_users(self) -> list[dict]:
        """返回所有管理员账号（含 hash），供上报同步给其他后台。"""
        with self._lock:
            return [{"username": u, "hash": d["hash"]}
                    for u, d in self._users.items() if d["role"] == "admin"]

    def add_user(self, username: str, password: str, role: str = "user") -> None:
        with self._lock:
            if username in self._users:
                raise ValueError(f"用户已存在: {username}")
            self._users[username] = {"hash": hash_password(password), "role": role}
            self._save_users(self._users)

    def set_password(self, username: str, password: str) -> None:
        with self._lock:
            if username not in self._users:
                raise ValueError(f"用户不存在: {username}")
            self._users[username]["hash"] = hash_password(password)
            self._save_users(self._users)

    def set_role(self, username: str, role: str) -> None:
        if role not in ("admin", "user"):
            raise ValueError("角色只能是 admin 或 user")
        with self._lock:
            if username not in self._users:
                raise ValueError(f"用户不存在: {username}")
            self._users[username]["role"] = role
            self._save_users(self._users)

    def delete_user(self, username: str) -> None:
        with self._lock:
            if username not in self._users:
                raise ValueError(f"用户不存在: {username}")
            admins = [u for u, d in self._users.items() if d["role"] == "admin" and u != username]
            if not admins:
                raise ValueError("至少保留一个管理员，禁止删除最后一个管理员")
            del self._users[username]
            self._save_users(self._users)

    def sync_admin_users(self, admin_users: list[dict], source: str = "") -> int:
        """合并其他服务端上报的管理员账号到本地用户表。
        source 为上报来源 reporter_id，用于追踪；该 source 不再上报某用户时自动清除。
        本地用户（无 _source）不受影响。
        """
        with self._lock:
            if source:
                to_remove = [u for u, d in self._users.items() if d.get("_source") == source]
                for u in to_remove:
                    del self._users[u]
            changed = False
            for u in admin_users:
                uname = u.get("username", "")
                uhash = u.get("hash", "")
                if not uname or not uhash:
                    continue
                existing = self._users.get(uname)
                if existing and not existing.get("_source"):
                    if existing["hash"] != uhash:
                        existing["hash"] = uhash
                        changed = True
                else:
                    self._users[uname] = {"hash": uhash, "role": "admin", "_source": source}
                    changed = True
            if changed:
                self._save_users(self._users)
            return sum(1 for d in self._users.values() if d.get("role") == "admin")

    # ---------- 存储相关 ----------
    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def modpacks_dir(self) -> str:
        return os.path.join(self.data_dir, "modpacks")

    @property
    def mods_dir(self) -> str:
        return os.path.join(self.data_dir, "mods")


settings = Settings()
