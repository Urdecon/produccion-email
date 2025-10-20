# domain/models.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class Attachment:
    filename: str
    content: bytes
    content_type: str

@dataclass
class MailItem:
    uid: int
    subject: str
    from_addr: str
    date_str: str
    attachments: list[Attachment]
