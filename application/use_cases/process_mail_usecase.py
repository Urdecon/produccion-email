# application/use_cases/process_mail_usecase.py
from __future__ import annotations
import fnmatch
import logging
from pathlib import Path
from typing import Literal
from domain.models import MailItem
from application.services.excel_to_payload import build_payload_from_excel
from application.services.etl_runner import run_etl_json

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
    ) -> None:
        self.allowed_senders = allowed_senders
        self.subject_filters = subject_filters
        self.allowed_exts = allowed_exts
        self.etl_cmd = etl_cmd
        self.etl_workdir = etl_workdir
        self.temp_storage_dir = temp_storage_dir

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

    def process_mail(self, mail: MailItem, saver) -> Outcome:
        # 1) Remitente permitido
        if not self._sender_ok(mail.from_addr):
            logger.info("Not processed (sender no permitido): %s", mail.from_addr)
            return "not_processed"

        # 2) Asunto (si configurado)
        if not self._subject_ok(mail.subject):
            logger.info("Not processed (asunto no coincide): %s", mail.subject)
            return "not_processed"

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
            return "not_processed"

        # 4) Procesar cada Excel
        all_ok = True
        for fp in excel_files:
            try:
                payload = build_payload_from_excel(fp)
                code, stdout, stderr = run_etl_json(payload, self.etl_cmd, self.etl_workdir)
                if code == 0:
                    logger.info("ETL OK %s: %s", fp.name, stdout.strip())
                else:
                    logger.error("ETL ERROR %s (code=%s): %s", fp.name, code, stderr.strip())
                    all_ok = False
            except Exception:
                logger.exception("Fallo procesando %s", fp.name)
                all_ok = False

        return "processed" if all_ok else "error"
