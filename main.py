# main.py
# Punto de entrada: loop de polling IMAP -> procesa correos -> lanza ETL
from __future__ import annotations
import logging
import time
from config.settings import Settings
from interface_adapters.controllers.polling_controller import PollingController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings()
    controller = PollingController(settings=settings)

    logger.info("=== Mail Ingestor ETL ===")
    logger.info("IMAP host=%s inbox=%s", settings.IMAP_HOST, settings.IMAP_FOLDER_INBOX)
    while True:
        try:
            controller.run_once()
        except Exception:
            logger.exception("Error en ciclo de polling")
        time.sleep(settings.POLL_INTERVAL)


if __name__ == "__main__":
    main()
