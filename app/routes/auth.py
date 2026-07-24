"""认证与用户管理路由。

读操作（同步 / 下载 / 状态）对客户端保持开放，仅写操作（上传 / 删除 / 修改）需要 token。
用户管理（改密码 / 增删用户）需要管理员 token。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from gpm_common import AuthError, create_token, decode_token, require_admin, require_token, route, verify_password

from app.config import settings


router = APIRouter()

# 改密码：任何登录用户可改自己的密码（含普通用户，客户端登录后也能改密）
_require_auth = Depends(require_token(settings.auth_secret))
# 用户管理（增删改查用户）：仅管理员
_require_admin = Depends(require_admin(settings.auth_secret))


# ---------- 登录 ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    expires_in: int


@router.post(route("/auth/login"), response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    """校验用户名密码，签发 JWT。"""
    stored_hash = settings.user_hash(req.username)
    if not stored_hash or not verify_password(req.password, stored_hash):
        raise AuthError("用户名或密码错误", status_code=401)
    role = settings.user_role(req.username) or "user"
    token = create_token({"sub": req.username, "role": role}, settings.auth_secret)
    return LoginResponse(token=token, username=req.username, role=role, expires_in=86400)


# ---------- 改自己的密码 ----------
class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.put(route("/auth/password"), dependencies=[_require_auth])
def change_password(req: ChangePasswordRequest, request: Request) -> dict:
    """修改当前登录用户密码。从 Authorization 头解析用户名。"""
    auth = request.headers.get("Authorization", "")
    token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else ""
    payload = decode_token(token, settings.auth_secret)
    username = getattr(payload, "sub", "")
    stored_hash = settings.user_hash(username)
    if not username or not stored_hash:
        raise AuthError("用户不存在", status_code=401)
    if not verify_password(req.old_password, stored_hash):
        raise AuthError("原密码错误", status_code=401)
    if len(req.new_password) < 6:
        raise AuthError("新密码至少 6 位", status_code=400)
    settings.set_password(username, req.new_password)
    return {"changed": username}


# ---------- 用户管理（管理员） ----------
class UserCreateRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class UserRoleUpdate(BaseModel):
    role: str  # "admin" | "user"


@router.get(route("/users"), dependencies=[_require_admin])
def list_users() -> dict:
    """列出所有用户名及角色（不返回 hash）。"""
    users = settings.users
    return {"users": [{"username": u, "role": d["role"]} for u, d in users.items()]}


@router.post(route("/users"), dependencies=[_require_admin])
def add_user(req: UserCreateRequest) -> dict:
    """新增用户，可指定是否管理员。"""
    if len(req.password) < 6:
        raise AuthError("密码至少 6 位", status_code=400)
    try:
        settings.add_user(req.username, req.password, role="admin" if req.is_admin else "user")
    except ValueError as e:
        raise AuthError(str(e), status_code=400)
    return {"created": req.username, "role": "admin" if req.is_admin else "user"}


@router.patch(route("/users/{username}"), dependencies=[_require_admin])
def update_user_role(username: str, req: UserRoleUpdate) -> dict:
    """修改用户角色（admin / user）。"""
    try:
        settings.set_role(username, req.role)
    except ValueError as e:
        raise AuthError(str(e), status_code=400)
    return {"username": username, "role": req.role}


@router.delete(route("/users/{username}"), dependencies=[_require_admin])
def delete_user(username: str) -> dict:
    """删除用户（至少保留一个管理员）。"""
    try:
        settings.delete_user(username)
    except ValueError as e:
        raise AuthError(str(e), status_code=400)
    return {"deleted": username}
