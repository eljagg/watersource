"""AQUARIUS Time-Series Publish API v2 client (ToR §E.1).

Endpoints (confirm against WRA's installed version during the design phase):
  POST /AQUARIUS/Publish/v2/session               -> token
  GET  /AQUARIUS/Publish/v2/GetLocationDescriptionList
  GET  /AQUARIUS/Publish/v2/GetTimeSeriesDescriptionList?LocationIdentifier=
  GET  /AQUARIUS/Publish/v2/GetTimeSeriesCorrectedData?TimeSeriesUniqueId=&QueryFrom=&QueryTo=
The read-only Publish API is preferred over direct SQL on the Aquarius
PostgreSQL 13 database because the vendor schema is not a supported interface.
"""
from __future__ import annotations

import requests
from django.conf import settings


class AquariusClient:
    def __init__(self):
        cfg = settings.AQUARIUS
        self.base = cfg["URL"].rstrip("/")
        self.user, self.password = cfg["USER"], cfg["PASSWORD"]
        self.session = requests.Session()
        self.token = None

    @property
    def enabled(self):
        return bool(self.base and self.user)

    def connect(self):
        r = self.session.post(f"{self.base}/AQUARIUS/Publish/v2/session", json={"Username": self.user, "Password": self.password}, timeout=30)
        r.raise_for_status()
        self.token = r.text.strip('"')
        self.session.headers["X-Authentication-Token"] = self.token

    def _get(self, path, **params):
        r = self.session.get(f"{self.base}/AQUARIUS/Publish/v2/{path}", params=params, timeout=120)
        r.raise_for_status()
        return r.json()

    def locations(self):
        return self._get("GetLocationDescriptionList").get("LocationDescriptions", [])

    def time_series_for(self, location_identifier):
        return self._get("GetTimeSeriesDescriptionList", LocationIdentifier=location_identifier).get("TimeSeriesDescriptions", [])

    def corrected_points(self, unique_id, query_from=None, query_to=None):
        params = {"TimeSeriesUniqueId": unique_id}
        if query_from:
            params["QueryFrom"] = query_from
        if query_to:
            params["QueryTo"] = query_to
        return self._get("GetTimeSeriesCorrectedData", **params).get("Points", [])
