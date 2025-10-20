# infrastructure/filesystem/storage.py
from __future__ import annotations
from pathlib import Path
import uuid

class TempStorage:
    def __init__(self, base: Path) -> None:
        self.base = base.resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, name_hint: str, data: bytes) -> Path:
        ext = "".join(Path(name_hint).suffixes) or ""
        fname = f"{uuid.uuid4().hex}{ext}"
        fp = self.base / fname
        fp.write_bytes(data)
        return fp
