from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings


_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class DatasetStorage:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        settings = get_settings()
        target = Path(base_dir or settings.dataset_storage_dir).expanduser()
        self._base_path = target.resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._base_path

    def dataset_dir(self, project_id: str, dataset_id: str) -> Path:
        directory = self._base_path / project_id / dataset_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_file(self, project_id: str, dataset_id: str, filename: str, file_data: bytes | BinaryIO) -> str:
        dataset_directory = self.dataset_dir(project_id, dataset_id)
        safe_name = self._sanitize_filename(filename) or "dataset.bin"
        target_path = dataset_directory / safe_name
        if isinstance(file_data, (bytes, bytearray)):
            target_path.write_bytes(bytes(file_data))
        else:
            with target_path.open("wb") as handle:
                shutil.copyfileobj(file_data, handle)
        return str(target_path.relative_to(self._base_path))

    def remove_dataset(self, project_id: str, dataset_id: str) -> None:
        directory = self._base_path / project_id / dataset_id
        if directory.exists():
            shutil.rmtree(directory)

    def resolve_path(self, relative_path: str) -> Path:
        return (self._base_path / relative_path).resolve()

    def _sanitize_filename(self, filename: str) -> str:
        name = filename.strip().replace(" ", "_")
        name = _SAFE_FILENAME_PATTERN.sub("_", name)
        return name[:255]


__all__ = ["DatasetStorage"]
