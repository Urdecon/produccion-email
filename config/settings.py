# config/settings.py
# config/settings.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "graph").lower()  # graph | imap

    # IMAP (por si mantienes fallback)
    IMAP_HOST: str = os.getenv("IMAP_HOST", "outlook.office365.com")
    IMAP_PORT: int = int(os.getenv("IMAP_PORT", 993))
    IMAP_USERNAME: str = os.getenv("IMAP_USERNAME", "")
    IMAP_PASSWORD: str = os.getenv("IMAP_PASSWORD", "")
    IMAP_SSL: bool = os.getenv("IMAP_SSL", "true").lower() == "true"
    IMAP_FOLDER_INBOX: str = os.getenv("IMAP_FOLDER_INBOX", "INBOX")
    IMAP_FOLDER_PROCESSED: str = os.getenv("IMAP_FOLDER_PROCESSED", "INBOX/Procesados")
    IMAP_FOLDER_ERROR: str = os.getenv("IMAP_FOLDER_ERROR", "INBOX/Errores")
    IMAP_FOLDER_NOT_PROCESSED: str = os.getenv("IMAP_FOLDER_NOT_PROCESSED", "INBOX/Not_Processed")

    # GRAPH
    GRAPH_TENANT_ID: str = os.getenv("GRAPH_TENANT_ID", "")
    GRAPH_CLIENT_ID: str = os.getenv("GRAPH_CLIENT_ID", "")
    GRAPH_CLIENT_SECRET: str = os.getenv("GRAPH_CLIENT_SECRET", "")
    GRAPH_USER_ID: str = os.getenv("GRAPH_USER_ID", "")
    GRAPH_BASE: str = os.getenv("GRAPH_BASE", "https://graph.microsoft.com/v1.0")
    GRAPH_FOLDER_INBOX: str = os.getenv("GRAPH_FOLDER_INBOX", "Inbox")
    GRAPH_FOLDER_PROCESSED: str = os.getenv("GRAPH_FOLDER_PROCESSED", "Inbox/Procesados")
    GRAPH_FOLDER_ERROR: str = os.getenv("GRAPH_FOLDER_ERROR", "Inbox/Errores")
    GRAPH_FOLDER_NOT_PROCESSED: str = os.getenv("GRAPH_FOLDER_NOT_PROCESSED", "Inbox/Not_Processed")

    # Filtros / adjuntos
    IMAP_ALLOWED_SENDERS: str = os.getenv("IMAP_ALLOWED_SENDERS", "")
    MAIL_SUBJECT_MATCH: str = os.getenv("MAIL_SUBJECT_MATCH", "")
    ATTACH_WHITELIST: str = os.getenv("ATTACH_WHITELIST", ".xlsx")
    TZ: str = os.getenv("TZ", "Europe/Madrid")

    # ETL
    ETL_WORKDIR: str = os.getenv("ETL_WORKDIR", "")
    ETL_RUN_CMD: str = os.getenv("ETL_RUN_CMD", "")

    # Polling
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", 30))
    MAX_MAILS_PER_LOOP: int = int(os.getenv("MAX_MAILS_PER_LOOP", 20))

    def allowed_senders(self) -> list[str]:
        raw = (self.IMAP_ALLOWED_SENDERS or "").strip()
        return [s.strip() for s in raw.split(",") if s.strip()]

    def subject_filters(self) -> list[str]:
        raw = (self.MAIL_SUBJECT_MATCH or "").strip()
        return [s.strip().lower() for s in raw.split(",") if s.strip()]

    def attach_exts(self) -> set[str]:
        return {e.strip().lower() for e in self.ATTACH_WHITELIST.split(",") if e.strip()}

    def etl_cmd_parts(self) -> list[str]:
        return [t for t in self.ETL_RUN_CMD.split(" ") if t.strip()]

    def etl_workdir_path(self) -> Path:
        return Path(self.ETL_WORKDIR).resolve()
