from __future__ import annotations

from pathlib import Path


class FileStorage:

    def __init__(self, sub_path: str | Path) -> None:
        from settings import get_app_settings

        self._root = get_app_settings().DATA_DIR / sub_path
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def set(self, key: str, data: bytes) -> Path:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def get(self, key: str) -> bytes | None:
        path = self._root / key
        return path.read_bytes() if path.exists() else None

    def delete(self, key: str) -> bool:
        path = self._root / key
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return (self._root / key).exists()

    def mtime(self, key: str) -> float | None:
        path = self._root / key
        return path.stat().st_mtime if path.exists() else None

    def list(self, pattern: str = "*") -> list[Path]:
        return list(self._root.glob(pattern))
