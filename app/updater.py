"""自动更新模块：定时检查 GitHub 仓库更新，有新提交时自动拉取并重启。

工作原理：
1. 后台线程每 update_interval 秒执行一次检查
2. 用 git fetch origin 获取远程最新提交，比较本地 HEAD 与 origin/main 的 SHA
3. 如果有更新：git pull 两个仓库 → 重新 pip install gpm-common → 进程退出
4. systemd 的 Restart=always 会自动拉起新版本

部署目录自动检测：gpm-web-admin 代码目录的父目录即为部署根目录。
典型路径：/opt/gpm/{gpm-web-admin, gpm-common, venv}
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# 自动检测部署目录
# __file__ = .../gpm-web-admin/app/updater.py
# 代码目录 = .../gpm-web-admin
# 部署目录 = 代码目录的父目录
_CODE_DIR = Path(__file__).resolve().parent.parent
_DEPLOY_DIR = _CODE_DIR.parent
_GPM_COMMON_DIR = _DEPLOY_DIR / "gpm-common"
_BRANCH = "main"

# 是否为打包环境（打包后不支持 git 更新）
_IS_COMPILED = "__compiled__" in dir()

# 默认检查间隔（秒）：5 分钟
_DEFAULT_INTERVAL = 300.0


class UpdateStatus:
    """线程安全的更新状态记录。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.last_check: float = 0.0
        self.last_result: str = "pending"  # pending / up_to_date / update_available / updating / updated / failed
        self.last_message: str = ""
        self.local_sha: str = ""
        self.remote_sha: str = ""
        self.auto_enabled: bool = True
        self.update_count: int = 0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "last_check": self.last_check,
                "last_check_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.last_check))
                                  if self.last_check else "—",
                "last_result": self.last_result,
                "last_message": self.last_message,
                "local_sha": self.local_sha[:8] if self.local_sha else "",
                "remote_sha": self.remote_sha[:8] if self.remote_sha else "",
                "auto_enabled": self.auto_enabled,
                "update_count": self.update_count,
                "branch": _BRANCH,
                "deploy_dir": str(_DEPLOY_DIR),
                "is_compiled": _IS_COMPILED,
            }

    def set(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)


# 全局状态单例
status = UpdateStatus()

# 后台线程控制
_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _run_git(args: list[str], cwd: str) -> tuple[int, str, str]:
    """执行 git 命令，返回 (exit_code, stdout, stderr)。"""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return -1, "", str(e)


def _git_sha(repo_dir: Path, ref: str = "HEAD") -> str:
    """获取指定 ref 的 commit SHA，失败返回空串。"""
    code, out, _ = _run_git(["rev-parse", ref], str(repo_dir))
    return out if code == 0 else ""


def check_for_updates() -> dict:
    """检查远程仓库是否有更新。不修改本地代码。

    返回 {"has_update": bool, "local_sha": str, "remote_sha": str, "message": str}
    """
    if _IS_COMPILED:
        return {"has_update": False, "local_sha": "", "remote_sha": "", "message": "打包环境不支持 git 更新"}

    if not _CODE_DIR.exists() or not _GPM_COMMON_DIR.exists():
        return {"has_update": False, "local_sha": "", "remote_sha": "", "message": "部署目录不存在"}

    # 检查是否是 git 仓库
    if not (_CODE_DIR / ".git").exists():
        return {"has_update": False, "local_sha": "", "remote_sha": "", "message": "非 git 仓库，无法检查更新"}

    local_sha = _git_sha(_CODE_DIR, "HEAD")

    # fetch 远程（不修改工作区）
    code, out, err = _run_git(["fetch", "origin", _BRANCH], str(_CODE_DIR))
    if code != 0:
        return {"has_update": False, "local_sha": local_sha, "remote_sha": "",
                "message": f"git fetch 失败: {err or out}"}

    remote_sha = _git_sha(_CODE_DIR, f"origin/{_BRANCH}")

    has_update = bool(local_sha and remote_sha and local_sha != remote_sha)

    msg = "有新版本可用" if has_update else "已是最新版本"
    return {"has_update": has_update, "local_sha": local_sha, "remote_sha": remote_sha, "message": msg}


def apply_update() -> dict:
    """应用更新：git pull 两个仓库 + 重新安装 gpm-common + 退出重启。

    返回 {"success": bool, "message": str}。成功后进程会退出，由 systemd 重启。
    """
    if _IS_COMPILED:
        return {"success": False, "message": "打包环境不支持 git 更新"}

    status.set(last_result="updating", last_message="正在拉取更新...")

    # 1. git pull gpm-common
    code, out, err = _run_git(["pull", "origin", _BRANCH], str(_GPM_COMMON_DIR))
    if code != 0:
        msg = f"gpm-common pull 失败: {err or out}"
        status.set(last_result="failed", last_message=msg)
        return {"success": False, "message": msg}

    # 2. git pull gpm-web-admin
    code, out, err = _run_git(["pull", "origin", _BRANCH], str(_CODE_DIR))
    if code != 0:
        msg = f"gpm-web-admin pull 失败: {err or out}"
        status.set(last_result="failed", last_message=msg)
        return {"success": False, "message": msg}

    status.set(last_message="正在重新安装依赖...")

    # 3. 重新安装 gpm-common（本地包，代码更新后需重装）
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", str(_GPM_COMMON_DIR)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            msg = f"gpm-common pip install 失败: {r.stderr[:200]}"
            status.set(last_result="failed", last_message=msg)
            return {"success": False, "message": msg}
    except subprocess.TimeoutExpired:
        msg = "gpm-common pip install 超时"
        status.set(last_result="failed", last_message=msg)
        return {"success": False, "message": msg}

    # 4. 更新 gpm-web-admin 依赖（requirements.txt 可能有变化）
    req_file = _CODE_DIR / "requirements.txt"
    if req_file.exists():
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(req_file)],
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            pass  # 依赖更新超时不阻断重启

    status.set(last_result="updated", last_message="更新完成，即将重启服务...", update_count=status.update_count + 1)

    # 5. 延迟 1 秒后退出，让 HTTP 响应先返回。systemd Restart=always 会拉起新版本。
    def _delayed_exit():
        time.sleep(1.0)
        # os._exit 绕过 atexit/shutdown 钩子，直接退出，systemd 立即重启
        os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()
    return {"success": True, "message": "更新完成，服务即将重启"}


def _auto_check_loop() -> None:
    """后台自动检查循环。"""
    while not _stop_event.is_set():
        try:
            if status.auto_enabled and not _IS_COMPILED:
                result = check_for_updates()
                status.set(
                    last_check=time.time(),
                    last_result="update_available" if result["has_update"] else "up_to_date",
                    last_message=result["message"],
                    local_sha=result["local_sha"],
                    remote_sha=result["remote_sha"],
                )
                if result["has_update"]:
                    apply_update()
        except Exception as e:  # noqa: BLE001
            status.set(last_check=time.time(), last_result="failed", last_message=f"自动检查异常: {e}")

        # 等待下次检查（可被 stop_event 提前唤醒）
        _stop_event.wait(_DEFAULT_INTERVAL)


def start_updater() -> None:
    """启动后台自动更新检查线程。"""
    global _thread
    if _IS_COMPILED:
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_auto_check_loop, daemon=True, name="gpm-updater")
    _thread.start()


def stop_updater() -> None:
    """停止后台线程。"""
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2)
