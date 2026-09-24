"""DSpace 6.x REST client (ToR G.1.iii, §E.3).

DSpace 6 REST: POST /rest/login (JSESSIONID cookie), POST /rest/collections/{id}/items,
POST /rest/items/{id}/bitstreams?name=... . DSpace 6 is end-of-life (July 2023);
the same interface (DSpaceClient) gets a second implementation for the DSpace 7+
REST contract when WRA upgrades — call sites do not change.
"""
from __future__ import annotations

import requests
from django.conf import settings


class DSpaceError(Exception):
    pass


class DSpaceClient:
    def __init__(self, base_url=None, user=None, password=None, collection_id=None, timeout=30):
        cfg = settings.DSPACE
        self.base = (base_url or cfg["URL"]).rstrip("/")
        self.user = user or cfg["USER"]
        self.password = password or cfg["PASSWORD"]
        self.collection_id = collection_id or cfg["COLLECTION_ID"]
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.base and self.user)

    def login(self):
        r = self.session.post(f"{self.base}/rest/login", data={"email": self.user, "password": self.password}, timeout=self.timeout)
        if r.status_code != 200:
            raise DSpaceError(f"login failed: {r.status_code}")

    def create_item(self, title: str, metadata: list[dict]) -> dict:
        body = {"name": title, "metadata": [{"key": "dc.title", "value": title}] + metadata}
        r = self.session.post(f"{self.base}/rest/collections/{self.collection_id}/items", json=body,
                              headers={"Accept": "application/json"}, timeout=self.timeout)
        if r.status_code not in (200, 201):
            raise DSpaceError(f"create item failed: {r.status_code} {r.text[:200]}")
        return r.json()

    def add_bitstream(self, item_id: str, filename: str, content: bytes, description: str = "") -> dict:
        r = self.session.post(f"{self.base}/rest/items/{item_id}/bitstreams", params={"name": filename, "description": description},
                              data=content, headers={"Accept": "application/json"}, timeout=self.timeout)
        if r.status_code not in (200, 201):
            raise DSpaceError(f"add bitstream failed: {r.status_code} {r.text[:200]}")
        return r.json()

    def logout(self):
        try:
            self.session.post(f"{self.base}/rest/logout", timeout=self.timeout)
        except requests.RequestException:
            pass


def archive_application_document(doc) -> str:
    """Create/append a DSpace item for the application and attach the file; return the handle."""
    client = DSpaceClient()
    if not client.enabled:
        return ""
    client.login()
    try:
        app = doc.application
        existing = app.documents.exclude(dspace_handle="").exclude(pk=doc.pk).first()
        if existing and existing.dspace_handle:
            # one DSpace item per application: look the item up by its handle and append the file
            handle = existing.dspace_handle
            r = client.session.get(f"{client.base}/rest/handle/{handle}", headers={"Accept": "application/json"}, timeout=client.timeout)
            if r.status_code != 200:
                raise DSpaceError(f"handle lookup failed: {r.status_code}")
            item = r.json()
            item_id = item.get("uuid") or item.get("id")
        else:
            item = client.create_item(f"Licence application {app.reference} — {app.applicant_name}", [
                {"key": "dc.identifier.other", "value": app.reference},
                {"key": "dc.type", "value": "Licence application"},
                {"key": "dc.date.issued", "value": app.created_at.date().isoformat()},
                {"key": "dc.description", "value": f"{app.get_water_source_display()} — {app.source_name}, {app.parish.name}"},
            ])
            handle = item.get("handle", "")
            item_id = item.get("uuid") or item.get("id")
        with doc.file.open("rb") as fh:
            client.add_bitstream(item_id, doc.original_name, fh.read(), description=doc.get_kind_display())
        return handle
    finally:
        client.logout()
