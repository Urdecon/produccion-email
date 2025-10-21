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

    # ETL (proyecto sharepoint_reader)
    ETL_WORKDIR: str = os.getenv("ETL_WORKDIR", "")
    ETL_RUN_CMD: str = os.getenv("ETL_RUN_CMD", "")  # p.ej.: C:/.../.venv/Scripts/python.exe -m interface_adapters.controllers.etl_api_entry
    ETL_TIMEOUT: int = int(os.getenv("ETL_TIMEOUT", "600"))

    # Polling
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", 30))
    MAX_MAILS_PER_LOOP: int = int(os.getenv("MAX_MAILS_PER_LOOP", 20))

    # ───────── SNAPSHOT (2º proceso) ─────────
    # Si está habilitado, se lanza SOLO tras ETL OK. Se infiere company/project/year/month del Excel.
    SNAPSHOT_ENABLED: bool = os.getenv("SNAPSHOT_ENABLED", "false").lower() == "true"
    SNAPSHOT_WORKDIR: str = os.getenv("SNAPSHOT_WORKDIR", "")  # raíz del repo snapshot
    SNAPSHOT_PY: str = os.getenv("SNAPSHOT_PY", "python")      # intérprete del venv del snapshot
    SNAPSHOT_TIMEOUT: int = int(os.getenv("SNAPSHOT_TIMEOUT", "900"))
    # Archivo/función de entrada: usaremos main.run_snapshot con -c (no necesitas crear puerta nueva de momento)
    # Si en un futuro creas un módulo propio (-m ...), podremos cambiar fácil la construcción del comando.

    # ───────── helpers ─────────
    def allowed_senders(self) -> list[str]:
        raw = (self.IMAP_ALLOWED_SENDERS or "").strip()
        return [s.strip() for s in raw.split(",") if s.strip()]

    def subject_filters(self) -> list[str]:
        raw = (self.MAIL_SUBJECT_MATCH or "").strip()
        return [s.strip().lower() for s in raw.split(",") if s.strip()]

    def attach_exts(self) -> set[str]:
        return {e.strip().lower() for e in self.ATTACH_WHITELIST.split(",") if e.strip()}

    def etl_cmd_parts(self) -> list[str]:
        # separa respetando comillas simples/dobles
        import shlex
        return shlex.split(self.ETL_RUN_CMD)

    def etl_workdir_path(self) -> Path:
        return Path(self.ETL_WORKDIR).resolve()

    def snapshot_workdir_path(self) -> Path:
        return Path(self.SNAPSHOT_WORKDIR).resolve()

    def snapshot_cmd_parts(self, company: str, project: str, year: int, month: int) -> list[str]:
        """
        Construye: <SNAPSHOT_PY> -c "from main import run_snapshot; run_snapshot(company='...', project='...', year=2025, month=8)"
        Ejecuta en SNAPSHOT_WORKDIR. No dependemos de tener un entrypoint -m ahora.
        """
        # Repr seguro por si hay espacios/comillas en los nombres
        code = (
            "from main import run_snapshot; "
            f"run_snapshot(company={company!r}, project={project!r}, year={int(year)}, month={int(month)})"
        )
        return [self.SNAPSHOT_PY, "-c", code]
