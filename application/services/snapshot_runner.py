# application/services/snapshot_runner.py
from __future__ import annotations
import subprocess
from pathlib import Path

def run_snapshot(
    *,
    python_exe: Path,
    workdir: Path,
    company: str,
    project: str,
    year: int,
    month: int,
    timeout: int | None = 900,
) -> tuple[int, str, str]:
    """
    Lanza el snapshot del repo externo SIN modificar su main.py:
    ejecuta: python -c "from main import run_snapshot; run_snapshot(...)" con cwd=workdir.

    Requisitos:
      - En workdir existe main.py con def run_snapshot(company, project, year, month)
    """
    code = (
        "from main import run_snapshot; "
        f"run_snapshot(company={company!r}, project={project!r}, year={year}, month={month})"
    )
    proc = subprocess.Popen(
        [str(python_exe), "-c", code],
        cwd=str(workdir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
