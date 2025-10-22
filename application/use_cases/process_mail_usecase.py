# application/use_cases/process_mail_usecase.py
from __future__ import annotations
import fnmatch
import logging
from pathlib import Path
from typing import Literal, Any

from domain.models import MailItem
from application.services.excel_to_payload import build_payload_from_excel
from application.services.etl_runner import run_etl_json
from application.services.snapshot_runner import run_snapshot

logger = logging.getLogger(__name__)

Outcome = Literal["processed", "not_processed", "error"]

class ProcessMailUseCase:
    def __init__(
        self,
        *,
        allowed_senders: list[str],
        subject_filters: list[str],
        allowed_exts: set[str],
        etl_cmd: list[str],
        etl_workdir: Path,
        temp_storage_dir: Path,
        etl_timeout: int = 600,
        # snapshot settings (opcionales; se pasan desde PollingController vía setattr si prefieres)
        snapshot_enabled: bool = False,
        snapshot_py: Path | None = None,
        snapshot_workdir: Path | None = None,
        snapshot_timeout: int = 900,
    ) -> None:
        self.allowed_senders = allowed_senders
        self.subject_filters = subject_filters
        self.allowed_exts = allowed_exts
        self.etl_cmd = etl_cmd
        self.etl_workdir = etl_workdir
        self.temp_storage_dir = temp_storage_dir
        self.etl_timeout = etl_timeout

        self.snapshot_enabled = snapshot_enabled
        self.snapshot_py = snapshot_py
        self.snapshot_workdir = snapshot_workdir
        self.snapshot_timeout = snapshot_timeout

    def _sender_ok(self, email: str) -> bool:
        if not self.allowed_senders:
            return True
        e = (email or "").lower()
        return any(fnmatch.fnmatch(e, pat.lower()) for pat in self.allowed_senders)

    def _subject_ok(self, subj: str) -> bool:
        if not self.subject_filters:
            return True
        s = (subj or "").lower()
        return any(token in s for token in self.subject_filters)

    def process_mail(self, mail: MailItem, saver) -> dict[str, Any]:
        """
        Devuelve: {
            "outcome": "processed" | "not_processed" | "error",
            "headers": [ {empresa, proyecto, fecha_seguimiento}, ...]  # uno por cada Excel válido
        }
        """
        # 1) Remitente permitido
        if not self._sender_ok(mail.from_addr):
            logger.info("Not processed (sender no permitido): %s", mail.from_addr)
            return {"outcome": "not_processed", "headers": []}

        # 2) Asunto (si configurado)
        if not self._subject_ok(mail.subject):
            logger.info("Not processed (asunto no coincide): %s", mail.subject)
            return {"outcome": "not_processed", "headers": []}

        # 3) Filtrar adjuntos .xlsx
        excel_files: list[Path] = []
        for att in mail.attachments:
            name = att.filename or ""
            if not any(name.lower().endswith(ext) for ext in self.allowed_exts):
                continue
            fp = saver(name, att.content)
            excel_files.append(fp)

        if not excel_files:
            logger.info("Not processed (sin adjuntos .xlsx válidos).")
            return {"outcome": "not_processed", "headers": []}

        # 4) Procesar cada Excel → ETL y (si procede) Snapshot
        all_ok = True
        headers: list[dict[str, str]] = []

        for fp in excel_files:
            try:
                payload = build_payload_from_excel(fp)
                # Guardamos cabeceras para notificaciones / snapshot
                hdr = (payload.get("payload", {}) or {}).get("header", {}) or {}
                headers.append({
                    "empresa": hdr.get("empresa") or "",
                    "proyecto": hdr.get("proyecto") or "",
                    "fecha_seguimiento": hdr.get("fecha_seguimiento") or "",
                })

                code, stdout, stderr = run_etl_json(payload, self.etl_cmd, self.etl_workdir)
                if code == 0:
                    logger.info("ETL OK %s: %s", fp.name, stdout.strip())
                else:
                    logger.error("ETL ERROR %s (code=%s): %s", fp.name, code, stderr.strip())
                    all_ok = False
                    continue  # no lanzar snapshot si ETL falla

                # ── SNAPSHOT ──
                if self.snapshot_enabled:
                    empresa = hdr.get("empresa")
                    proyecto = hdr.get("proyecto")
                    fecha = hdr.get("fecha_seguimiento")
                    if not (empresa and proyecto and fecha):
                        logger.error("Snapshot SKIP %s: faltan datos header (empresa/proyecto/fecha_seguimiento).", fp.name)
                        all_ok = False
                    else:
                        try:
                            y = int(fecha[-4:])        # "01/MM/YYYY" → YYYY
                            m = int(fecha[3:5])        # → MM
                            rc, so, se = run_snapshot(
                                python_exe=self.snapshot_py,          # type: ignore[arg-type]
                                workdir=self.snapshot_workdir,        # type: ignore[arg-type]
                                company=empresa,
                                project=proyecto,
                                year=y,
                                month=m,
                                timeout=self.snapshot_timeout,
                            )
                            if rc == 0:
                                logger.info("Snapshot OK %s: %s", fp.name, (so or "").strip() or "OK")
                            else:
                                logger.error("Snapshot ERROR %s (code=%s): %s", fp.name, rc, (se or so or "").strip())
                                all_ok = False
                        except Exception:
                            logger.exception("Snapshot EXCEPTION %s", fp.name)
                            all_ok = False

            except Exception:
                logger.exception("Fallo procesando %s", fp.name)
                all_ok = False

        return {"outcome": "processed" if all_ok else "error", "headers": headers}
