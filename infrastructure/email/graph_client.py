# infrastructure/email/graph_client.py
# infrastructure/email/graph_client.py
from __future__ import annotations
import logging
from typing import List, Dict, Any
import base64
import requests
import msal

logger = logging.getLogger(__name__)

class GraphMailClient:
    def __init__(self, *, tenant_id: str, client_id: str, client_secret: str, user_id: str, base: str = "https://graph.microsoft.com/v1.0") -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self.base = base.rstrip("/")
        self._token: str | None = None

    def _acquire_token(self) -> str:
        if self._token:
            return self._token
        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
        )
        # Application permissions: Mail.ReadWrite
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(f"MSAL token error: {result}")
        self._token = result["access_token"]
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._acquire_token()}"}

    def _get(self, url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        r = requests.get(url, headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, url: str, json: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(url, headers={**self._headers(), "Content-Type": "application/json"}, json=json, timeout=30)
        r.raise_for_status()
        return r.json()

    def _patch(self, url: str, json: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.patch(url, headers={**self._headers(), "Content-Type": "application/json"}, json=json, timeout=30)
        r.raise_for_status()
        return r.json() if r.text else {}

    # --- Folder helpers ---
    def get_folder_id_by_path(self, path: str) -> str:
        """
        path ejemplo:
          - 'inbox'                -> usa well-known name (recomendado)
          - 'inbox/Procesados'     -> 'Procesados' colgando de Inbox
          - 'Inbox/Procesados'     -> también soportado (normaliza a well-known si coincide)
          - 'Bandeja de entrada/Procesados' -> soportado si el primer segmento no es well-known

        Reglas:
          - Si el primer segmento es un well-known (inbox, sentitems, drafts, deleteditems, archive, junkemail, outbox),
            se usa directamente /mailFolders('name').
          - Si no lo es, se intenta localizar por displayName (insensible a mayúsculas).
          - Para cada segmento hijo, se localiza por displayName. Si no existe, se crea.
        """
        parts = [p for p in (path or "").split("/") if p]
        if not parts:
            raise RuntimeError("Ruta de carpeta vacía")

        # 1) Resolver raíz
        well_known = {
            "inbox", "sentitems", "drafts", "deleteditems",
            "archive", "junkemail", "outbox",
        }
        root_seg = parts[0].strip()
        root_id: str | None = None

        if root_seg.lower() in well_known:
            # /users/{id}/mailFolders('inbox')
            url = f"{self.base}/users/{self.user_id}/mailFolders('{root_seg.lower()}')"
            root = self._get(url)
            root_id = root.get("id")
            if not root_id:
                raise RuntimeError(f"No se pudo resolver well-known folder '{root_seg}'")
        else:
            # Buscar por displayName en raíz de mailFolders
            root_list = self._get(f"{self.base}/users/{self.user_id}/mailFolders").get("value", [])
            for f in root_list:
                if (f.get("displayName") or "").lower() == root_seg.lower():
                    root_id = f.get("id")
                    break
            # Si además root_seg es "Inbox" (texto) lo normalizamos a well-known 'inbox'
            if not root_id and root_seg.lower() == "inbox":
                url = f"{self.base}/users/{self.user_id}/mailFolders('inbox')"
                root = self._get(url)
                root_id = root.get("id")

            if not root_id:
                raise RuntimeError(f"No se encontró carpeta raíz '{root_seg}'")

        # 2) Descender por hijos (displayName). Crear si no existe.
        current_id = root_id
        for name in parts[1:]:
            children = self._get(f"{self.base}/users/{self.user_id}/mailFolders/{current_id}/childFolders").get("value", [])
            next_id = None
            for f in children:
                if (f.get("displayName") or "").lower() == name.lower():
                    next_id = f.get("id")
                    break
            if not next_id:
                created = self._post(
                    f"{self.base}/users/{self.user_id}/mailFolders/{current_id}/childFolders",
                    {"displayName": name}
                )
                next_id = created.get("id")
            current_id = next_id

        return current_id

    # --- Listar correos no leídos en una carpeta ---
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

    # --- Obtener adjuntos de un mensaje ---
    def get_message_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        url = f"{self.base}/users/{self.user_id}/messages/{message_id}/attachments"
        data = self._get(url)
        return data.get("value", [])

    # --- Descargar attachment binario (fileAttachment) ---
    @staticmethod
    def decode_attachment(att: Dict[str, Any]) -> tuple[str, bytes, str]:
        name = att.get("name") or "adjunto"
        ctype = att.get("contentType") or "application/octet-stream"
        if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
            content_bytes = base64.b64decode(att["contentBytes"])
            return name, content_bytes, ctype
        # ItemAttachment (otro mail/calendario) se ignora
        return name, b"", ctype

    # --- Mover mensaje a otra carpeta ---
    def move_message(self, message_id: str, dest_folder_path: str) -> None:
        dest_id = self.get_folder_id_by_path(dest_folder_path)
        url = f"{self.base}/users/{self.user_id}/messages/{message_id}/move"
        self._post(url, {"destinationId": dest_id})
