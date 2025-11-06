# infrastructure/email/graph_client.py
from __future__ import annotations
import logging
import base64
from typing import List, Dict, Any, Iterable, Tuple, Optional
import requests
import msal
import time

logger = logging.getLogger(__name__)

class GraphMailClient:
    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        user_id: str,
        base: str = "https://graph.microsoft.com/v1.0"
    ) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self.base = base.rstrip("/")
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ───────── auth ─────────
    def _acquire_token(self) -> str:
        """
        Obtiene un access_token de MSAL y controla la caducidad.
        Reutiliza el token si le queda más de 60 s de vida.
        """
        now = time.time()
        if self._token and (self._token_expires_at - 60) > now:
            return self._token

        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
        )

        # Intento silencioso (si MSAL tiene caché in-memory) y, si no, solicitud normal.
        result = app.acquire_token_silent(scopes=["https://graph.microsoft.com/.default"], account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" not in result:
            raise RuntimeError(f"MSAL token error: {result}")

        self._token = result["access_token"]
        self._token_expires_at = now + float(result.get("expires_in", 3600))
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._acquire_token()}"}


    # ───────── HTTP helpers ─────────
    def _get(self, url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        r = requests.get(url, headers=self._headers(), params=params, timeout=30)
        if r.status_code == 401:
            # Token caducado → forzamos refresh y reintentamos UNA vez
            self._token = None
            self._token_expires_at = 0.0
            r = requests.get(url, headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, url: str, json: Dict[str, Any]) -> requests.Response:
        """Devuelve el Response (Graph puede responder 202 sin cuerpo)."""
        headers = {**self._headers(), "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=json, timeout=30)
        if r.status_code == 401:
            self._token = None
            self._token_expires_at = 0.0
            headers = {**self._headers(), "Content-Type": "application/json"}
            r = requests.post(url, headers=headers, json=json, timeout=30)
        r.raise_for_status()
        return r

    def _patch(self, url: str, json: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        headers = {**self._headers(), "Content-Type": "application/json"}
        r = requests.patch(url, headers=headers, json=json, timeout=30)
        if r.status_code == 401:
            self._token = None
            self._token_expires_at = 0.0
            headers = {**self._headers(), "Content-Type": "application/json"}
            r = requests.patch(url, headers=headers, json=json, timeout=30)
        r.raise_for_status()
        return r.json() if (r.text and r.headers.get("Content-Type", "").startswith("application/json")) else None

    # ───────── folders ─────────
    def get_folder_id_by_path(self, path: str) -> str:
        parts = [p for p in (path or "").split("/") if p]
        if not parts:
            raise RuntimeError("Ruta de carpeta vacía")

        well_known = {"inbox", "sentitems", "drafts", "deleteditems", "archive", "junkemail", "outbox"}
        root_seg = parts[0].strip()

        if root_seg.lower() in well_known or root_seg.lower() == "inbox":
            root = self._get(f"{self.base}/users/{self.user_id}/mailFolders('inbox')")
            root_id = root.get("id")
        else:
            root_list = self._get(f"{self.base}/users/{self.user_id}/mailFolders").get("value", [])
            root_id = next((f.get("id") for f in root_list if (f.get("displayName") or "").lower() == root_seg.lower()), None)

        if not root_id:
            raise RuntimeError(f"No se encontró carpeta raíz '{root_seg}'")

        current_id = root_id
        for name in parts[1:]:
            children = self._get(f"{self.base}/users/{self.user_id}/mailFolders/{current_id}/childFolders").get("value", [])
            next_id = next((f.get("id") for f in children if (f.get("displayName") or "").lower() == name.lower()), None)
            if not next_id:
                created = self._post(
                    f"{self.base}/users/{self.user_id}/mailFolders/{current_id}/childFolders",
                    {"displayName": name}
                )
                next_id = created.json().get("id") if created.text else None
            current_id = next_id
        return current_id

    # ───────── list / attachments ─────────
    def list_unread(self, folder_path: str, top: int = 20) -> List[Dict[str, Any]]:
        fid = self.get_folder_id_by_path(folder_path)
        url = f"{self.base}/users/{self.user_id}/mailFolders/{fid}/messages"
        params = {
            "$top": top,
            "$filter": "isRead eq false",
            "$select": "id,subject,from,receivedDateTime,hasAttachments",
            "$orderby": "receivedDateTime asc",
        }
        data = self._get(url, params=params)
        return data.get("value", [])

    def get_message_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        url = f"{self.base}/users/{self.user_id}/messages/{message_id}/attachments"
        data = self._get(url)
        return data.get("value", [])

    @staticmethod
    def decode_attachment(att: Dict[str, Any]) -> tuple[str, bytes, str]:
        name = att.get("name") or "adjunto"
        ctype = att.get("contentType") or "application/octet-stream"
        if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
            content_bytes = base64.b64decode(att["contentBytes"])
            return name, content_bytes, ctype
        return name, b"", ctype

    def move_message(self, message_id: str, dest_folder_path: str) -> None:
        dest_id = self.get_folder_id_by_path(dest_folder_path)
        url = f"{self.base}/users/{self.user_id}/messages/{message_id}/move"
        self._post(url, {"destinationId": dest_id})

    # ───────── enviar emails (sin parsear JSON: Graph responde 202) ─────────
    def send_mail(
        self,
        *,
        to: Iterable[str],
        subject: str,
        body_text: str,
        attachments: Iterable[Tuple[str, bytes, str]] = (),
    ) -> None:
        msg = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body_text},
                "toRecipients": [{"emailAddress": {"address": a}} for a in to],
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": name,
                        "contentType": ctype or "application/octet-stream",
                        "contentBytes": base64.b64encode(data).decode("ascii"),
                    }
                    for (name, data, ctype) in attachments
                ],
            },
            "saveToSentItems": True,
        }
        url = f"{self.base}/users/{self.user_id}/sendMail"
        r = self._post(url, json=msg)
        # OK typical: 202 Accepted with empty body
        if r.status_code not in (200, 202):
            logger.warning("send_mail status=%s body=%s", r.status_code, r.text or "<empty>")
