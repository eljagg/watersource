"""WRA's published GIS on the Government of Jamaica ArcGIS Online (v0.11.0).

The Water Resources Authority publishes its basins, watershed management
units, rivers, gauging stations and 2018 hydrostratigraphy as public ArcGIS
feature services under the Government of Jamaica organisation
(``goj.maps.arcgis.com``). :func:`fetch` pages through one layer and returns
GeoJSON in WGS 84; :data:`SERVICES` says where each of our layers comes from.

Terms (service description): "No data is to be shared or edited without
permission from the Water Resources Authority." The data is public-read and
this is WRA's own system; attribution is kept on every feature.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

ORG = "https://services6.arcgis.com/3R3y1KXaPJ9BFnsU/arcgis/rest/services"
SOURCE = "WRA, Government of Jamaica ArcGIS Online"
PAGE = 1000
USER_AGENT = "WaterSource/0.11 (Water Resources Authority licensing and data system)"

#: our layer → (service path, name fields in order of preference, id fields in order of preference)
SERVICES = {
    "basins": ("Hydrologic_Basins/FeatureServer/0", ("Hydrobasin",), ("BasinNo", "FID")),
    "wmus": ("Watershed_Management_Units/FeatureServer/0", ("Wmu_Name",), ("Wmu_No", "FID")),
    "subwmus": ("Ground_and_Surface_Water_Monitoring_Network__Jamaica_WFL1/FeatureServer/5", ("Sub_WMU", "SUB_WMU", "Name", "NAME"), ("OBJECTID", "FID")),
    "rivers": ("Rivers_and_Streams_in_Jamaica_WFL1/FeatureServer/2", ("NAME", "Name", "RIVER", "River"), ("OBJECTID", "FID")),
    "gauges": ("Water_Resources/FeatureServer/0", ("STATION", "Station", "NAME", "Name", "STN_NAME", "NEWSTNCODE"), ("NEWSTNCODE", "OBJECTID", "FID")),
    "hydrostrat": ("Water_Resources/FeatureServer/5", ("HYDRO_STRA",), ("OBJECTID", "FID")),
}


def query_url(service: str, offset: int = 0, page: int = PAGE) -> str:
    """The paged GeoJSON query for one service layer."""
    q = {"where": "1=1", "outFields": "*", "outSR": "4326", "f": "geojson", "geometryPrecision": "5", "resultOffset": str(offset), "resultRecordCount": str(page)}
    return f"{ORG}/{service}/query?{urllib.parse.urlencode(q)}"


def fetch(service: str, timeout: int = 60, opener=None) -> list[dict]:
    """All features of ``service`` as GeoJSON features (WGS 84), following ArcGIS paging."""
    opener = opener or _http_get
    feats: list[dict] = []
    offset = 0
    while True:
        data = json.loads(opener(query_url(service, offset), timeout))
        if "error" in data:
            raise RuntimeError(f"ArcGIS error for {service}: {data['error']}")
        page = data.get("features") or []
        feats.extend(page)
        more = (data.get("properties") or {}).get("exceededTransferLimit") or data.get("exceededTransferLimit")
        if not page or (len(page) < PAGE and not more):
            break
        offset += len(page)
    return feats


def _http_get(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - fixed https host
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310
        return resp.read().decode("utf-8")


def pick(props: dict, candidates: tuple[str, ...], default: str = "") -> str:
    """First non-blank property among ``candidates`` (case-insensitive)."""
    lower = {k.lower(): v for k, v in props.items()}
    for c in candidates:
        v = lower.get(c.lower())
        if v is not None and str(v).strip():
            return str(v).strip()
    return default
