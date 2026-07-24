"""整合包路由：上传 / 列表 / 详情 / 下载 / 删除。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from gpm_common import GamePushError, ModpackCreate, require_admin, route
from gpm_common.protocol import ErrorCode

from app import storage
from app.config import settings
from app.server_info import server_info


router = APIRouter()

# 写操作（上传 / 删除 / 修改）需要管理员 token；读操作（列表 / 详情 / 下载）对客户端开放
_require_admin = Depends(require_admin(settings.auth_secret))


def _form_field(value: str | None, default: str = "") -> str:
    return value if value is not None else default


@router.get(route("/modpacks"))
def list_modpacks():
    return {"modpacks": [m.model_dump() for m in storage.list_modpacks()]}


@router.post(route("/modpacks"), dependencies=[_require_admin])
async def upload_modpack(
    file: UploadFile = File(...),
    name: str = Form(...),
    version: str = Form(...),
    game: str = Form(...),
    game_version: str = Form(""),
    mod_loader: str = Form("auto"),
    mod_loader_version: str | None = Form(None),
    description: str = Form(""),
):
    # 校验大小
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise GamePushError(
            f"File too large: {len(content)} bytes",
            code=ErrorCode.FILE_TOO_LARGE,
            status_code=413,
        )

    # 写入临时文件后交给 storage 层
    import os
    import tempfile

    fd, tmp_path = tempfile.mkstemp(prefix="gpm_upload_", suffix="_" + (file.filename or ""))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)

        # 自动识别：表单 game_version 留空或 mod_loader 为 auto 时，解析整合包 manifest 填充
        auto_detected = False
        if not game_version or mod_loader in ("", "auto"):
            try:
                from gpm_common import GameAdapterRegistry

                adapter = GameAdapterRegistry.get(game)
                if adapter is not None:
                    detected = adapter.detect_metadata(tmp_path)
                    if detected:
                        auto_detected = True
                        if not game_version and detected.get("game_version"):
                            game_version = detected["game_version"]
                        if mod_loader in ("", "auto") and detected.get("mod_loader"):
                            mod_loader = detected["mod_loader"]
                            # 仅当用户未手动指定 mod_loader_version 时用识别值
                            if not mod_loader_version and detected.get("mod_loader_version"):
                                mod_loader_version = detected["mod_loader_version"]
            except Exception:  # noqa: BLE001
                # 识别失败不应阻断上传，回退到表单原值
                pass

        meta_fields = {
            "name": name,
            "version": version,
            "game": game,
            "game_version": game_version,
            "mod_loader": mod_loader,
            "mod_loader_version": mod_loader_version,
            "description": description,
        }
        modpack = storage.save_modpack(meta_fields, tmp_path, file.filename or "modpack.zip")
        server_info.record_upload()
        result = modpack.model_dump()
        result["auto_detected"] = auto_detected
        return result
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.get(route("/modpacks/{item_id}"))
def get_modpack(item_id: str):
    return storage.get_modpack(item_id).model_dump()


@router.patch(route("/modpacks/{item_id}"), dependencies=[_require_admin])
def update_modpack(item_id: str, fields: dict):
    """修改整合包元数据 / 上下架状态。"""
    return storage.update_modpack(item_id, fields).model_dump()


@router.get(route("/modpacks/{item_id}/download"))
def download_modpack(item_id: str):
    modpack = storage.get_modpack(item_id)
    path = storage.modpack_file_path(item_id)
    server_info.record_download()
    return FileResponse(path, filename=modpack.file_name)


@router.delete(route("/modpacks/{item_id}"), dependencies=[_require_admin])
def delete_modpack(item_id: str):
    storage.delete_modpack(item_id)
    return {"deleted": item_id}
