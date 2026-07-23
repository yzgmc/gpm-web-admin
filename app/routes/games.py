"""游戏列表路由。返回当前已注册适配器支持的游戏。"""

from __future__ import annotations

from fastapi import APIRouter

from gpm_common import GameAdapterRegistry, route

router = APIRouter()


@router.get(route("/games"))
def list_games():
    return {"games": [g.model_dump() for g in GameAdapterRegistry.all_games()]}
