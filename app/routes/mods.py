"""模组路由：上传 / 列表 / 详情 / 下载 / 删除。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from gpm_common import GamePushError, require_admin, route
from gpm_common.protocol import ErrorCode

from app import storage
from app.config import settings
from app.server_info import server_info


router = APIRouter()

# 写操作需要管理员 token；读操作对客户端开放
_require_admin = Depends(require_admin(settings.auth_secret))


@router.get(route("/mods"))
def list_mods():
    return {"mods": [m.model_dump() for m in storage.list_mods()]}


@router.post(route("/mods"), dependencies=[_require_admin])
async def upload_mod(
    file: UploadFile = File(...),
    name: str = Form(...),
    version: str = Form(...),
    game: str = Form(...),
    game_version: str = Form(""),
    mod_loader: str = Form("auto"),
    mod_loader_version: str | None = Form(None),
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

        # 自动识别：表单 game_version 留空或 mod_loader 为 auto 时，解析模组 jar 元数据填充
        auto_detected = False
        if not game_version or mod_loader in ("", "auto"):
            try:
                from gpm_common import GameAdapterRegistry

                adapter = GameAdapterRegistry.get(game)
                if adapter is not None and hasattr(adapter, "detect_mod_metadata"):
                    detected = adapter.detect_mod_metadata(tmp_path)
                    if detected:
                        auto_detected = True
                        if not game_version and detected.get("game_version"):
                            game_version = detected["game_version"]
                        if mod_loader in ("", "auto") and detected.get("mod_loader"):
                            mod_loader = detected["mod_loader"]
                            if not mod_loader_version and detected.get("mod_loader_version"):
                                mod_loader_version = detected["mod_loader_version"]
            except Exception:  # noqa: BLE001
                pass

        meta_fields = {
            "name": name,
            "version": version,
            "game": game,
            "game_version": game_version,
            "mod_loader": mod_loader,
            "mod_loader_version": mod_loader_version,
            "modpack_id": modpack_id,
            "description": description,
        }
        mod = storage.save_mod(meta_fields, tmp_path, file.filename or "mod.jar")
        server_info.record_upload()
        result = mod.model_dump()
        result["auto_detected"] = auto_detected
        return result
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.get(route("/mods/{item_id}"))
def get_mod(item_id: str):
    return storage.get_mod(item_id).model_dump()


@router.patch(route("/mods/{item_id}"), dependencies=[_require_admin])
def update_mod(item_id: str, fields: dict):
    """修改模组元数据 / 上下架状态。"""
    return storage.update_mod(item_id, fields).model_dump()


@router.get(route("/mods/{item_id}/download"))
def download_mod(item_id: str):
    mod = storage.get_mod(item_id)
    path = storage.mod_file_path(item_id)
    server_info.record_download()
    return FileResponse(path, filename=mod.file_name)


@router.delete(route("/mods/{item_id}"), dependencies=[_require_admin])
def delete_mod(item_id: str):
    storage.delete_mod(item_id)
    return {"deleted": item_id}
