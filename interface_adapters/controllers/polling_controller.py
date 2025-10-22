# interface_adapters/controllers/polling_controller.py
from __future__ import annotations
import logging
from pathlib import Path
from datetime import datetime, timezone
from config.settings import Settings
from infrastructure.filesystem.storage import TempStorage
from application.use_cases.process_mail_usecase import ProcessMailUseCase
from domain.models import MailItem, Attachment
from utils.log_capture import MailRunLogCapture

from infrastructure.email.graph_client import GraphMailClient
from infrastructure.email.imap_client import IMAPInbox  # opcional

logger = logging.getLogger(__name__)

class PollingController:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tmp = TempStorage(base=Path("./_tmp"))
        self.uc = ProcessMailUseCase(
            allowed_senders=settings.allowed_senders(),
            subject_filters=settings.subject_filters(),
            allowed_exts=settings.attach_exts(),
            etl_cmd=settings.etl_cmd_parts(),
            etl_workdir=settings.etl_workdir_path(),
            temp_storage_dir=Path("./_tmp").resolve(),
            etl_timeout=settings.ETL_TIMEOUT,
            snapshot_enabled=settings.SNAPSHOT_ENABLED,
            snapshot_py=settings.snapshot_python_path(),
            snapshot_workdir=settings.snapshot_workdir_path(),
            snapshot_timeout=settings.SNAPSHOT_TIMEOUT,
        )

        if self.settings.EMAIL_PROVIDER == "graph":
            self.client = GraphMailClient(
                tenant_id=settings.GRAPH_TENANT_ID,
                client_id=settings.GRAPH_CLIENT_ID,
                client_secret=settings.GRAPH_CLIENT_SECRET,
                user_id=settings.GRAPH_USER_ID,
                base=settings.GRAPH_BASE,
            )
        else:
            self.client = None

    # ───────────────────────── notificaciones ─────────────────────────
    def _send_log_outputs(self, *, subject: str, log_text: str) -> None:
        """
        Solo envía el log a informatica@… (no autoenvía, para evitar loops).
        """
        st = self.settings
        if st.LOG_MODE not in ("email", "both"):
            return
        try:
            log_bytes = log_text.encode("utf-8", errors="replace")
            fname = f"log_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
            self.client.send_mail(
                to=[st.LOG_EMAIL_TO],
                subject=subject,
                body_text="Adjunto log de la ejecución.",
                attachments=[(fname, log_bytes, "text/plain")],
            )
            logger.info("Log enviado a %s", st.LOG_EMAIL_TO)
        except Exception:
            logger.exception("No se pudo enviar el log por email")

    def _send_success_to_sender(self, *, sender: str, project: str, fecha_registro: str) -> None:
        if not self.settings.SUCCESS_NOTIFY or not sender:
            return
        try:
            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            subj = f"✅ Producción registrada: {project} — {fecha_registro}"
            body = (
                f"Hola,\n\n"
                f"El proceso de registro de la producción del proyecto {project} "
                f"con fecha de registro {fecha_registro} se ha completado con éxito.\n\n"
                f"Fecha y hora de ejecución: {ahora}\n\n"
                f"Un saludo."
            )
            self.client.send_mail(to=[sender], subject=subj, body_text=body)
            logger.info("Aviso de éxito enviado a %s", sender)
        except Exception:
            logger.exception("No se pudo enviar el email de éxito al remitente")

    # ───────────────────────── ejecución ─────────────────────────
    def _process_mail_graph(self, item: dict) -> str:
        mid = item["id"]
        subject = item.get("subject") or ""
        sender = (item.get("from", {}) or {}).get("emailAddress", {}).get("address", "")
        attachments_raw = self.client.get_message_attachments(mid)

        attachments: list[Attachment] = []
        for ar in attachments_raw:
            name, content, ctype = self.client.decode_attachment(ar)
            if content:
                attachments.append(Attachment(filename=name, content=content, content_type=ctype))

        mail = MailItem(uid=0, subject=subject, from_addr=sender, date_str="", attachments=attachments)

        with MailRunLogCapture() as cap:
            logger.info("=== Procesando correo de %s — asunto: %s ===", sender, subject)
            result = self.uc.process_mail(mail, saver=lambda name, data: self.tmp.save_bytes(name, data))
            outcome = result.get("outcome", "not_processed")
            log_subject = f"[LOG] Ingesta {outcome.upper()} — remitente {sender or '-'} — asunto {subject or '-'}"
            self._send_log_outputs(subject=log_subject, log_text=cap.text())

        # Mover correo según resultado
        st = self.settings
        try:
            dest = (
                st.GRAPH_FOLDER_PROCESSED if outcome == "processed"
                else st.GRAPH_FOLDER_NOT_PROCESSED if outcome == "not_processed"
                else st.GRAPH_FOLDER_ERROR
            )
            self.client.move_message(mid, dest)
            logger.info("Movido '%s' -> %s", subject, dest)
        except Exception:
            logger.exception("No se pudo mover el correo tras el procesamiento")

        # Notificar éxito
        if outcome == "processed":
            headers = [h for h in result.get("headers", []) if h]
            hdr = headers[0] if headers else {}
            project = hdr.get("proyecto") or "N/D"
            fecha_reg = hdr.get("fecha_seguimiento") or "N/D"
            self._send_success_to_sender(sender=sender, project=project, fecha_registro=fecha_reg)

        return outcome

    def run_once(self) -> None:
        st = self.settings
        if st.EMAIL_PROVIDER == "graph":
            items = self.client.list_unread(st.GRAPH_FOLDER_INBOX, top=st.MAX_MAILS_PER_LOOP)
            if not items:
                logger.info("Sin correos nuevos (Graph).")
                return
            logger.info("Procesando %d correos (Graph)…", len(items))
            for it in items:
                try:
                    self._process_mail_graph(it)
                except Exception:
                    logger.exception("Error procesando correo %s", it.get("id"))
            return

        # IMAP (opcional)
        with IMAPInbox(st.IMAP_HOST, st.IMAP_PORT, st.IMAP_USERNAME, st.IMAP_PASSWORD, st.IMAP_SSL) as inbox:
            inbox.select_folder(st.IMAP_FOLDER_INBOX)
            uids = inbox.search_unseen(limit=st.MAX_MAILS_PER_LOOP)
            if not uids:
                logger.info("Sin correos nuevos (IMAP).")
                return
            logger.info("Procesando %d correos (IMAP)…", len(uids))
            for uid in uids:
                mail = inbox.fetch_mail(uid)
                with MailRunLogCapture() as cap:
                    result = self.uc.process_mail(mail, saver=lambda name, data: self.tmp.save_bytes(name, data))
                    outcome = result.get("outcome", "not_processed")
                    self._send_log_outputs(subject=f"[LOG] Ingesta {outcome.upper()} (IMAP)", log_text=cap.text())
                dest = (
                    st.IMAP_FOLDER_PROCESSED if outcome == "processed"
                    else st.IMAP_FOLDER_NOT_PROCESSED if outcome == "not_processed"
                    else st.IMAP_FOLDER_ERROR
                )
                try:
                    inbox.move_to(uid, dest)
                except Exception:
                    logger.exception("No se pudo mover UID=%s", uid)
