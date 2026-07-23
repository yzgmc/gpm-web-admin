"""元数据与文件存储后端。

每个整合包 / 模组在存储目录下有自己的子目录，包含：
- meta.json：元数据
- 实际文件

通过 meta.json 持久化，避免引入数据库依赖，便于备份与排查。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from gpm_common import (
    GameAdapterRegistry,
    GamePushError,
    Mod,
    Modpack,
    build_meta_path,
    build_storage_path,
    compute_sha256,
    dir_size,
    ensure_dir,
    safe_join,
)
from gpm_common.protocol import ErrorCode

from app.config import settings


KIND_MODPACKS = "modpacks"
KIND_MODS = "mods"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


def _meta_path(kind: str, item_id: str) -> str:
    return build_meta_path(settings.data_dir, kind, item_id)


def _file_path(kind: str, item_id: str, file_name: str) -> str:
    return build_storage_path(settings.data_dir, kind, item_id, file_name)


def _read_meta(kind: str, item_id: str) -> dict:
    path = _meta_path(kind, item_id)
    if not os.path.exists(path):
        raise GamePushError(
            f"{kind[:-1]} not found: {item_id}",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_meta(kind: str, item_id: str, meta: dict) -> None:
    path = _meta_path(kind, item_id)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, default=str)


def _list_meta(kind: str) -> list[dict]:
    base = os.path.join(settings.data_dir, kind)
    if not os.path.isdir(base):
        return []
    result = []
    for entry in os.listdir(base):
        meta_file = os.path.join(base, entry, "meta.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    result.append(json.load(f))
            except (OSError, json.JSONDecodeError):
                continue
    return result


# ----------------------------- Modpacks -----------------------------

def save_modpack(meta_fields: dict, uploaded_file_path: str, original_filename: str) -> Modpack:
    """保存上传的整合包。meta_fields 来自表单字段，uploaded_file_path 是临时文件路径。"""
    game = meta_fields.get("game", "")
    adapter = GameAdapterRegistry.require(game)
    if not adapter.validate_modpack(uploaded_file_path):
        raise GamePushError(
            f"Modpack validation failed for game {game}",
            code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    item_id = _new_id()
    file_name = os.path.basename(original_filename) or f"{item_id}.zip"
    dest_path = _file_path(KIND_MODPACKS, item_id, file_name)
    ensure_dir(os.path.dirname(dest_path))
    _move_file(uploaded_file_path, dest_path)

    file_size = os.path.getsize(dest_path)
    file_hash = compute_sha256(dest_path)
    now = _now()

    modpack = Modpack(
        id=item_id,
        name=meta_fields["name"],
        version=meta_fields["version"],
        game=game,
        game_version=meta_fields["game_version"],
        mod_loader=meta_fields.get("mod_loader", "vanilla"),
        mod_loader_version=meta_fields.get("mod_loader_version"),
        description=meta_fields.get("description", ""),
        file_name=file_name,
        file_size=file_size,
        file_hash=file_hash,
        created_at=now,
        updated_at=now,
    )
    _write_meta(KIND_MODPACKS, item_id, modpack.model_dump())
    return modpack


def list_modpacks() -> list[Modpack]:
    return [Modpack(**m) for m in _list_meta(KIND_MODPACKS)]


def get_modpack(item_id: str) -> Modpack:
    return Modpack(**_read_meta(KIND_MODPACKS, item_id))


def modpack_file_path(item_id: str) -> str:
    modpack = get_modpack(item_id)
    path = _file_path(KIND_MODPACKS, item_id, modpack.file_name)
    if not os.path.exists(path):
        raise GamePushError(
            f"Modpack file missing on disk: {item_id}",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )
    return path


def delete_modpack(item_id: str) -> None:
    # 先校验存在
    get_modpack(item_id)
    base = safe_join(settings.data_dir, KIND_MODPACKS, item_id)
    import shutil

    if os.path.isdir(base):
        shutil.rmtree(base)


def update_modpack(item_id: str, fields: dict) -> Modpack:
    """修改整合包元数据（名称/版本/描述/上下架状态等），刷新 updated_at。"""
    modpack = get_modpack(item_id)
    data = modpack.model_dump()
    # 仅允许修改这些字段
    for k in ("name", "version", "game", "game_version", "mod_loader",
              "mod_loader_version", "description", "enabled"):
        if k in fields:
            data[k] = fields[k]
    data["updated_at"] = _now()
    _write_meta(KIND_MODPACKS, item_id, data)
    return Modpack(**data)


# ----------------------------- Mods -----------------------------

def save_mod(meta_fields: dict, uploaded_file_path: str, original_filename: str) -> Mod:
    game = meta_fields.get("game", "")
    adapter = GameAdapterRegistry.require(game)
    if not adapter.validate_mod(uploaded_file_path):
        raise GamePushError(
            f"Mod validation failed for game {game}",
            code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    item_id = _new_id()
    file_name = os.path.basename(original_filename) or f"{item_id}.jar"
    dest_path = _file_path(KIND_MODS, item_id, file_name)
    ensure_dir(os.path.dirname(dest_path))
    _move_file(uploaded_file_path, dest_path)

    file_size = os.path.getsize(dest_path)
    file_hash = compute_sha256(dest_path)
    now = _now()

    mod = Mod(
        id=item_id,
        name=meta_fields["name"],
        version=meta_fields["version"],
        game=game,
        modpack_id=meta_fields.get("modpack_id"),
        description=meta_fields.get("description", ""),
        file_name=file_name,
        file_size=file_size,
        file_hash=file_hash,
        created_at=now,
        updated_at=now,
    )
    _write_meta(KIND_MODS, item_id, mod.model_dump())
    return mod


def list_mods() -> list[Mod]:
    return [Mod(**m) for m in _list_meta(KIND_MODS)]


def get_mod(item_id: str) -> Mod:
    return Mod(**_read_meta(KIND_MODS, item_id))


def mod_file_path(item_id: str) -> str:
    mod = get_mod(item_id)
    path = _file_path(KIND_MODS, item_id, mod.file_name)
    if not os.path.exists(path):
        raise GamePushError(
            f"Mod file missing on disk: {item_id}",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )
    return path


def delete_mod(item_id: str) -> None:
    get_mod(item_id)
    base = safe_join(settings.data_dir, KIND_MODS, item_id)
    import shutil

    if os.path.isdir(base):
        shutil.rmtree(base)


def update_mod(item_id: str, fields: dict) -> Mod:
    """修改模组元数据，刷新 updated_at。"""
    mod = get_mod(item_id)
    data = mod.model_dump()
    for k in ("name", "version", "game", "modpack_id", "description", "enabled"):
        if k in fields:
            data[k] = fields[k]
    data["updated_at"] = _now()
    _write_meta(KIND_MODS, item_id, data)
    return Mod(**data)


# ----------------------------- 统计 -----------------------------

def storage_used_bytes() -> int:
    return dir_size(settings.data_dir)


def _move_file(src: str, dst: str) -> None:
    ensure_dir(os.path.dirname(dst))
    try:
        os.replace(src, dst)
    except OSError:
        # 跨盘符时 replace 失败，回退到复制 + 删除
        import shutil

        shutil.copyfile(src, dst)
        os.remove(src)
