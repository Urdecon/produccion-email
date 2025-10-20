# infrastructure/email/imap_client.py
from __future__ import annotations
import logging
from typing import Iterable
from imapclient import IMAPClient
import pyzmail
from domain.models import MailItem, Attachment

logger = logging.getLogger(__name__)

class IMAPInbox:
    def __init__(self, host: str, port: int, user: str, password: str, ssl: bool = True) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
        self.client: IMAPClient | None = None

    def __enter__(self) -> "IMAPInbox":
        self.client = IMAPClient(self.host, port=self.port, ssl=self.ssl)
        self.client.login(self.user, self.password)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.client:
                self.client.logout()
        except Exception:
            logger.exception("Error cerrando IMAP")

    def select_folder(self, folder: str) -> None:
        assert self.client
        self.client.select_folder(folder, readonly=False)

    def search_unseen(self, limit: int | None = None) -> list[int]:
        assert self.client
        uids = self.client.search(["UNSEEN"])
        uids = sorted(uids)  # procesar en orden
        if limit:
            uids = uids[:limit]
        return uids

    def fetch_mail(self, uid: int) -> MailItem:
        assert self.client
        resp = self.client.fetch([uid], ["RFC822"])[uid]
        msg = pyzmail.PyzMessage.factory(resp[b"RFC822"])

        subject = msg.get_subject() or ""
        from_addr = msg.get_addresses("from")[0][1] if msg.get_addresses("from") else ""
        date_str = str(msg.get_decoded_header("date") or "")

        atts: list[Attachment] = []
        for part in msg.mailparts:
            if part.is_body:
                continue
            fname = part.filename or "adjunto"
            ctype = part.type or "application/octet-stream"
            payload = part.get_payload()
            if isinstance(payload, bytes):
                atts.append(Attachment(filename=fname, content=payload, content_type=ctype))

        return MailItem(uid=uid, subject=subject, from_addr=from_addr, date_str=date_str, attachments=atts)

    def mark_seen(self, uid: int) -> None:
        assert self.client
        self.client.add_flags([uid], [b"\\Seen"])

    def move_to(self, uid: int, dest_folder: str) -> None:
        assert self.client
        self.client.move([uid], dest_folder)

    def idle_wait_new(self, timeout_seconds: int = 1500) -> bool:
        """
        Entra en modo IDLE y espera notificación de nuevos correos hasta 'timeout_seconds'.
        Devuelve True si se recibió notificación, False si expiró.
        """
        assert self.client
        try:
            self.client.idle()
            logger.info("Entrando en IDLE (%s s)…", timeout_seconds)
            responses = self.client.idle_check(timeout=timeout_seconds)
            self.client.idle_done()
            if responses:
                # Cualquier notificación: revisaremos UNSEEN
                logger.info("Notificación IMAP: %s", responses[:3])
                return True
            return False
        except Exception:
            logger.exception("Fallo en IDLE; saliendo de IDLE")
            try:
                self.client.idle_done()
            except Exception:
                pass
            return False
