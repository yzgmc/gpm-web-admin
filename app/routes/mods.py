"""模组路由：上传 / 列表 / 详情 / 下载 / 删除。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from gpm_common import GamePushError, require_token, route
from gpm_common.protocol import ErrorCode

from app import storage
from app.config import settings
from app.server_info import server_info


router = APIRouter()

# 写操作需要登录 token；读操作对客户端开放
_require_auth = Depends(require_token(settings.auth_secret))


@router.get(route("/mods"))
def list_mods():
    return {"mods": [m.model_dump() for m in storage.list_mods()]}


@router.post(route("/mods"), dependencies=[_require_auth])
async def upload_mod(
    file: UploadFile = File(...),
    name: str = Form(...),
    version: str = Form(...),
    game: str = Form(...),
    modpack_id: str | None = Form(None),
    description: str = Form(""),
):
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise GamePushError(
            f"File too large: {len(content)} bytes",
            code=ErrorCode.FILE_TOO_LARGE,
            status_code=413,
        )

    import os
    import tempfile

    fd, tmp_path = tempfile.mkstemp(prefix="gpm_mod_", suffix="_" + (file.filename or ""))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        meta_fields = {
            "name": name,
            "version": version,
            "game": game,
            "modpack_id": modpack_id,
            "description": description,
        }
        mod = storage.save_mod(meta_fields, tmp_path, file.filename or "mod.jar")
        server_info.record_upload()
        return mod.model_dump()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.get(route("/mods/{item_id}"))
def get_mod(item_id: str):
    return storage.get_mod(item_id).model_dump()


@router.patch(route("/mods/{item_id}"), dependencies=[_require_auth])
def update_mod(item_id: str, fields: dict):
    """修改模组元数据 / 上下架状态。"""
    return storage.update_mod(item_id, fields).model_dump()


@router.get(route("/mods/{item_id}/download"))
def download_mod(item_id: str):
    mod = storage.get_mod(item_id)
    path = storage.mod_file_path(item_id)
    server_info.record_download()
    return FileResponse(path, filename=mod.file_name)


@router.delete(route("/mods/{item_id}"), dependencies=[_require_auth])
def delete_mod(item_id: str):
    storage.delete_mod(item_id)
    return {"deleted": item_id}
