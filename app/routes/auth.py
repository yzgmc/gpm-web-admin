"""认证路由：管理员登录签发 JWT。

仪表盘 API（GET /api/v1/dashboard）需要 token；上报接收（POST /api/v1/report）对各
上报端保持开放，无需登录。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from gpm_common import AuthError, create_token, verify_password

from app.config import settings


router = APIRouter(prefix="/api/v1")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    expires_in: int


@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    """校验管理员用户名密码，签发 JWT。"""
    stored = settings.users.get(req.username)
    if not stored or not verify_password(req.password, stored):
        raise AuthError("用户名或密码错误", status_code=401)
    token = create_token({"sub": req.username, "role": "admin"}, settings.auth_secret)
    return LoginResponse(
        token=token,
        username=req.username,
        role="admin",
        expires_in=86400,
    )
