"""Map page, GeoJSON layers and the GIS package download (v0.7.0)."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts import roles
from apps.core.restrict import can_see_restricted

from . import layers

CACHE_SECONDS = 600


def _map_context(request, **extra):
    ws = settings.WATERSOURCE
    import json

    return {"tiles_url": ws["MAP_TILES_URL"], "tiles_attribution": ws["MAP_TILES_ATTRIBUTION"], "map_center": ws["MAP_CENTER"], "map_zoom": ws["MAP_ZOOM"],
            "basemaps_json": json.dumps(ws["MAP_BASEMAPS"]),
            "exact_coordinates": can_see_restricted(request.user), "can_export": _export_allowed(request.user), **extra}


@require_GET
def index(request):
    """Interactive map: parishes, basins, WMUs coloured by utilisation, aquifers and sites."""
    return render(request, "maps/index.html", _map_context(request))


@require_GET
def full(request):
    """The map alone, edge to edge, for a large screen or TV (no navigation; layers refresh every five minutes)."""
    return render(request, "maps/full.html", _map_context(request))


@require_GET
def layer(request, layer):
    """One GeoJSON layer (WGS 84). Boundaries are public; site coordinates are masked per viewer."""
    fn = layers.LAYERS.get(layer)
    if fn is None:
        raise Http404
    data = fn(request.user)
    resp = JsonResponse(data)
    resp["Content-Type"] = "application/geo+json"
    resp["Cache-Control"] = "private, max-age=60"
    return resp


# -- GeoPackage export ---------------------------------------------------------------------

#: layer name → SQL (storage SRID; ogr2ogr reprojects to the requested SRID)
GPKG_LAYERS = {
    "parishes": "SELECT code, name, geom_source, geom FROM ref_parish WHERE geom IS NOT NULL",
    "basins": "SELECT code, name, geom_source, geom FROM ref_basin WHERE geom IS NOT NULL",
    "wmus": "SELECT w.code, w.name, b.name AS basin, w.safe_yield_m3_d, w.geom_source, w.geom FROM ref_wmu w LEFT JOIN ref_basin b ON b.id = w.basin_id WHERE w.geom IS NOT NULL",
    "aquifers": "SELECT a.code, a.name, a.aquifer_type, a.safe_yield_m3_d, b.name AS basin, a.geom_source, a.geom FROM ref_aquifer a "
                "LEFT JOIN ref_basin b ON b.id = a.basin_id WHERE a.geom IS NOT NULL",
    "wells": "SELECT w.id, w.name, w.use, w.is_public_supply, w.easting, w.northing, w.elevation_m, p.name AS parish, b.name AS basin, m.name AS wmu, "
             "w.classification, w.location AS geom FROM ref_well w LEFT JOIN ref_parish p ON p.id = w.parish_id LEFT JOIN ref_basin b ON b.id = w.basin_id "
             "LEFT JOIN ref_wmu m ON m.id = w.wmu_id WHERE w.location IS NOT NULL AND NOT w.is_abandoned",
    "stations": "SELECT s.id, s.name, s.is_public_supply, s.easting, s.northing, s.elevation_m, p.name AS parish, r.name AS river, s.classification, s.location AS geom "
                "FROM ref_streamflowstation s LEFT JOIN ref_parish p ON p.id = s.parish_id LEFT JOIN ref_river r ON r.id = s.river_id WHERE s.location IS NOT NULL AND s.is_active",
    "springs": "SELECT s.id, s.name, p.name AS parish, s.location AS geom FROM ref_spring s LEFT JOIN ref_parish p ON p.id = s.parish_id WHERE s.location IS NOT NULL",
    "licences": "SELECT l.number, l.status, l.daily_volume_granted_m3, l.issued_on, l.expires_on, m.name AS wmu, w.name AS well, w.location AS geom "
                "FROM lic_licence l LEFT JOIN ref_wmu m ON m.id = l.wmu_id LEFT JOIN ref_well w ON w.id = l.well_id WHERE w.location IS NOT NULL",
}
SRIDS = {"3448": "JAD2001 (EPSG:3448)", "4326": "WGS 84 (EPSG:4326)"}


def _pg_conn() -> str:
    db = settings.DATABASES["default"]
    parts = [f"dbname={db['NAME']}"]
    for key, opt in (("USER", "user"), ("PASSWORD", "password"), ("HOST", "host"), ("PORT", "port")):
        if db.get(key):
            parts.append(f"{opt}={db[key]}")
    return "PG:" + " ".join(parts)


def _gpkg_cache_path(srid: str) -> Path:
    tag = hashlib.sha256(f"{settings.DATABASES['default']['NAME']}-{srid}".encode()).hexdigest()[:10]
    return Path(tempfile.gettempdir()) / f"watersource-{tag}.gpkg"


def build_geopackage(srid: str = "3448", force: bool = False) -> Path:
    """Write every layer into one GeoPackage with ``ogr2ogr``; cached for ``CACHE_SECONDS``."""
    out = _gpkg_cache_path(srid)
    if not force and out.exists() and time.time() - out.stat().st_mtime < CACHE_SECONDS:
        return out
    ogr = shutil.which("ogr2ogr")
    if ogr is None:
        raise RuntimeError("ogr2ogr (GDAL) is not installed on this server.")
    tmp = out.with_suffix(".building.gpkg")
    tmp.unlink(missing_ok=True)
    for name, sql in GPKG_LAYERS.items():
        cmd = [ogr, "-f", "GPKG", str(tmp), _pg_conn(), "-sql", sql, "-nln", name, "-t_srs", f"EPSG:{srid}", "-s_srs", "EPSG:3448", "-lco", "GEOMETRY_NAME=geom"]
        if tmp.exists():
            cmd.insert(1, "-update")
        subprocess.run(cmd, check=True, capture_output=True, timeout=120, env={**os.environ, "PGPASSWORD": settings.DATABASES["default"].get("PASSWORD", "")})  # noqa: S603 — fixed argv, no shell
    os.replace(tmp, out)
    return out


def _export_allowed(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.has_role(*roles.GIS_EXPORT_ROLES))


@login_required
@require_GET
def export_index(request):
    """GIS package page: what is in it, which grid, download."""
    if not _export_allowed(request.user):
        raise Http404
    return render(request, "maps/export.html", _map_context(request, layers=list(GPKG_LAYERS), srids=SRIDS))


@login_required
@require_GET
def export_gpkg(request):
    """Download the GeoPackage (technical staff only — it carries exact coordinates of every site)."""
    if not _export_allowed(request.user):
        raise Http404
    srid = request.GET.get("srid", "3448")
    if srid not in SRIDS:
        raise Http404
    try:
        path = build_geopackage(srid, force=request.GET.get("refresh") == "1")
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = exc.stderr.decode(errors="replace")[-400:] if getattr(exc, "stderr", None) else str(exc)
        return render(request, "maps/export.html", _map_context(request, layers=list(GPKG_LAYERS), srids=SRIDS, error=detail), status=503)
    from apps.core.audit import log

    log("maps.gis_export", summary=f"GeoPackage downloaded (EPSG:{srid})", actor=request.user)
    resp = FileResponse(open(path, "rb"), as_attachment=True, filename=f"watersource-{srid}.gpkg", content_type="application/geopackage+sqlite3")
    return resp
