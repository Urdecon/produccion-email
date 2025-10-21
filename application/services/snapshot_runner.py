# application/services/snapshot_runner.py
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Sequence

def run_snapshot(
    *,
    cmd_parts: Sequence[str],
    workdir: Path,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """
    Lanza el snapshot como subproceso.
    - cmd_parts: lista ya construida (ver Settings.snapshot_cmd_parts)
    - workdir: carpeta raíz del repo snapshot
    """
    proc = subprocess.Popen(
        list(cmd_parts),
        cwd=str(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=None,
    )
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
