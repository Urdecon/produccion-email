# interface_adapters/controllers/polling_controller.py
from __future__ import annotations
import logging
from pathlib import Path
from config.settings import Settings
from infrastructure.filesystem.storage import TempStorage
from application.use_cases.process_mail_usecase import ProcessMailUseCase
from domain.models import MailItem, Attachment

# Proveedores
from infrastructure.email.graph_client import GraphMailClient
from infrastructure.email.imap_client import IMAPInbox  # opcional fallback

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
            # ── snapshot (2º proceso) ──
            snapshot_enabled=settings.SNAPSHOT_ENABLED,
            snapshot_cmd_builder=settings.snapshot_cmd_parts,
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
            self.client = None  # usaremos IMAP más abajo si quieres

    def _process_mailitem(self, mail: MailItem) -> str:
        outcome = self.uc.process_mail(
            mail, saver=lambda name, data: self.tmp.save_bytes(name, data)
        )
        return outcome

    def run_once(self) -> None:
        st = self.settings

        if st.EMAIL_PROVIDER == "graph":
            items = self.client.list_unread(st.GRAPH_FOLDER_INBOX, top=st.MAX_MAILS_PER_LOOP)
            if not items:
                logger.info("Sin correos nuevos (Graph).")
                return

            logger.info("Procesando %d correos (Graph)…", len(items))
            for item in items:
                mid = item["id"]
                subject = item.get("subject") or ""
                from_addr = (item.get("from", {}) or {}).get("emailAddress", {}).get("address", "")
                atts_raw = self.client.get_message_attachments(mid)
                attachments: list[Attachment] = []
                for ar in atts_raw:
                    name, content, ctype = self.client.decode_attachment(ar)
                    if content:
                        attachments.append(Attachment(filename=name, content=content, content_type=ctype))
                mail = MailItem(uid=0, subject=subject, from_addr=from_addr, date_str="", attachments=attachments)

                try:
                    outcome = self._process_mailitem(mail)
                    if outcome == "processed":
                        dest = st.GRAPH_FOLDER_PROCESSED
                    elif outcome == "not_processed":
                        dest = st.GRAPH_FOLDER_NOT_PROCESSED
                    else:
                        dest = st.GRAPH_FOLDER_ERROR
                    self.client.move_message(mid, dest)
                    logger.info("Movido %s -> %s", subject, dest)
                except Exception:
                    logger.exception("Fallo procesando %s; moviendo a errores", subject)
                    try:
                        self.client.move_message(mid, st.GRAPH_FOLDER_ERROR)
                    except Exception:
                        logger.exception("No se pudo mover a errores en Graph")
            return

        # ---- OPCIONAL: modo IMAP si quisieras mantenerlo ----
        with IMAPInbox(st.IMAP_HOST, st.IMAP_PORT, st.IMAP_USERNAME, st.IMAP_PASSWORD, st.IMAP_SSL) as inbox:
            inbox.select_folder(st.IMAP_FOLDER_INBOX)
            uids = inbox.search_unseen(limit=st.MAX_MAILS_PER_LOOP)
            if not uids:
                logger.info("Sin correos nuevos (IMAP).")
                return
            logger.info("Procesando %d correos (IMAP)…", len(uids))
            for uid in uids:
                mail = inbox.fetch_mail(uid)
                try:
                    outcome = self._process_mailitem(mail)
                    if outcome == "processed":
                        dest = st.IMAP_FOLDER_PROCESSED
                    elif outcome == "not_processed":
                        dest = st.IMAP_FOLDER_NOT_PROCESSED
                    else:
                        dest = st.IMAP_FOLDER_ERROR
                    inbox.move_to(uid, dest)
                except Exception:
                    logger.exception("Fallo IMAP con UID=%s", uid)
                    try:
                        inbox.move_to(uid, st.IMAP_FOLDER_ERROR)
                    except Exception:
                        logger.exception("No se pudo mover a errores")
