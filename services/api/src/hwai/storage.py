"""Local file storage under DATA_DIR/<user_id>/<kind>/<uuid>.<ext>.

The client filename is never used; the extension comes from content sniffing.
All paths are stored relative to DATA_DIR and checked to stay inside it.
"""

import shutil
import uuid
from pathlib import Path

from hwai.config import get_settings


def _root() -> Path:
    return get_settings().data_dir.resolve()


def _resolve(rel_path: str) -> Path:
    root = _root()
    path = (root / rel_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("path escapes DATA_DIR")
    return path


def save_file(user_id: str, kind: str, data: bytes, ext: str) -> str:
    """Store bytes and return the path relative to DATA_DIR."""
    if not user_id.isalnum() or not kind.isalnum() or not ext.isalnum():
        raise ValueError("invalid storage path component")
    rel = f"{user_id}/{kind}/{uuid.uuid4().hex}.{ext}"
    path = _resolve(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def read_file(rel_path: str) -> bytes:
    return _resolve(rel_path).read_bytes()


def absolute_path(rel_path: str) -> Path:
    return _resolve(rel_path)


def delete_file(rel_path: str) -> None:
    _resolve(rel_path).unlink(missing_ok=True)


def write_file(rel_path: str, data: bytes) -> None:
    """Write bytes at a path (relative to DATA_DIR) that the caller chose."""
    path = _resolve(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def delete_tree(rel_dir: str) -> None:
    """Remove a directory (relative to DATA_DIR) and everything under it, if it exists."""
    path = _resolve(rel_dir)
    if path == _root():
        raise ValueError("refusing to delete DATA_DIR itself")
    shutil.rmtree(path, ignore_errors=True)
