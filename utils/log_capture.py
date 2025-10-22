# utils/log_capture.py

from __future__ import annotations
import io
import logging

class MailRunLogCapture:
    """
    Captura temporal del log (root) a un buffer en memoria para adjuntarlo al finalizar.
    Uso:
        with MailRunLogCapture() as cap:
            ... # ejecutar proceso
            text = cap.text()
    """
    def __init__(self, level=logging.INFO) -> None:
        self.level = level
        self.buffer = io.StringIO()
        self.handler = logging.StreamHandler(self.buffer)
        self.handler.setLevel(level)
        self.handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    def __enter__(self):
        root = logging.getLogger()
        self._prev_level = root.level
        root.setLevel(min(self._prev_level, self.level) if self._prev_level else self.level)
        root.addHandler(self.handler)
        return self

    def __exit__(self, exc_type, exc, tb):
        root = logging.getLogger()
        try:
            root.removeHandler(self.handler)
        finally:
            self.handler.close()

    def text(self) -> str:
        return self.buffer.getvalue()
