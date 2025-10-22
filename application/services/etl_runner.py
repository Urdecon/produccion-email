# application/services/etl_runner.py

from __future__ import annotations
import json
import subprocess
from typing import Any
from pathlib import Path

def run_etl_json(payload: dict[str, Any], cmd_parts: list[str], workdir: Path, timeout: int = 0) -> tuple[int, str, str]:
    proc = subprocess.Popen(
        cmd_parts,
        cwd=str(workdir),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8-sig")  # BOM por compat
    try:
        out, err = proc.communicate(input=body, timeout=timeout if timeout and timeout > 0 else None)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return 124, out.decode("utf-8", "replace"), (err.decode("utf-8", "replace") or "ETL TIMEOUT")
    return proc.returncode, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
