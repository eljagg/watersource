"""Public-data exports for ArcGIS Enterprise (Addendum 1 §9) and Finance (ToR H.xiii)."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.obs.models import AbstractionRecord
from apps.ref.models import StreamflowStation, Well


def _out_dir(sub: str) -> Path:
    p = Path(settings.EXPORT_DIR) / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


def _feature(obj, props, geom_field="geom4326"):
    g = getattr(obj, geom_field, None)
    return {"type": "Feature", "geometry": json.loads(g.geojson) if g else None, "properties": props}


def _public_point(site):
    """Point for export: exact for ordinary sites, snapped to the public grid for public-supply sources (ADR-0002)."""
    from django.contrib.gis.geos import Point

    from apps.core.restrict import mask_site

    m = mask_site(site, None)
    if m["easting"] is None or m["northing"] is None:
        return None
    pt = Point(float(m["easting"]), float(m["northing"]), srid=3448)
    pt.transform(4326)
    return pt


def export_public_geojson() -> list[str]:
    """Only rows in public views (approved + public) leave the system; public-supply coordinates are coarsened."""
    stamp = timezone.now().strftime("%Y%m%d")
    out = _out_dir("arcgis")
    files = []
    wells = Well.objects.public().select_related("parish", "basin", "wmu")
    feats = []
    for w in wells:
        w.geom4326 = _public_point(w)
        feats.append(_feature(w, {"name": w.name, "parish": w.parish.name if w.parish_id else None, "basin": w.basin.name if w.basin_id else None,
                                  "wmu": w.wmu.name if w.wmu_id else None,
                                  "elevation_m": None if w.is_public_supply else (float(w.elevation_m) if w.elevation_m is not None else None),
                                  "use": w.use, "status": "abandoned" if w.is_abandoned else "in_use", "coordinates_coarsened": w.is_public_supply}))
    path = out / f"wells_public_{stamp}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:4326"}}, "features": feats}))
    files.append(str(path))
    stations = StreamflowStation.objects.public().select_related("parish", "river")
    feats = []
    for st in stations:
        st.geom4326 = _public_point(st)
        feats.append(_feature(st, {"name": st.name, "river": st.river.name if st.river_id else None, "parish": st.parish.name if st.parish_id else None,
                                   "coordinates_coarsened": st.is_public_supply}))
    path = out / f"streamflow_stations_public_{stamp}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    files.append(str(path))
    return files


def export_finance_csv(period_start, period_end) -> str:
    """Licence, licensee, period, granted, abstracted, over-limit — for volume-based fees."""
    out = _out_dir("finance")
    path = out / f"abstraction_{period_start:%Y%m%d}_{period_end:%Y%m%d}.csv"
    qs = (AbstractionRecord.objects.approved().filter(period_start__gte=period_start, period_end__lte=period_end)
          .select_related("licence__licensee", "licence__parish"))
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["licence_number", "licensee", "parish", "period_start", "period_end", "daily_volume_granted_m3", "abstraction_volume_m3", "over_limit", "over_limit_pct"])
        for r in qs:
            w.writerow([r.licence.number if r.licence_id else "", r.licence.licensee.name if r.licence_id else "", r.licence.parish.name if r.licence_id else "",
                        r.period_start.isoformat(), r.period_end.isoformat(), r.daily_volume_granted_m3, r.abstraction_volume_m3, r.over_limit, r.over_limit_pct or ""])
    os.chmod(path, 0o640)
    return str(path)


# ---------------------------------------------------------------------------
# On-demand Finance export (ToR H.xiii; stakeholder model: Finance & Accounts consumes licence/abstraction via API/CSV)
# ---------------------------------------------------------------------------
FINANCE_LICENCE_COLUMNS = ["licence_number", "licensee", "licensee_email", "parish", "wmu", "water_source", "source_name", "purpose",
                           "daily_volume_granted_m3", "issued_on", "expires_on", "status"]
FINANCE_ABSTRACTION_COLUMNS = ["licence_number", "licensee", "parish", "period_start", "period_end", "days", "daily_volume_granted_m3",
                               "abstraction_volume_m3", "daily_equivalent_m3", "over_limit", "over_limit_pct"]


def finance_licence_rows(status: str | None = None):
    """Rows for the licence register export (active by default)."""
    from apps.lic.models import Licence, LicenceStatus

    qs = Licence.objects.select_related("licensee", "parish", "wmu").order_by("number")
    qs = qs.filter(status=status) if status else qs.filter(status=LicenceStatus.ACTIVE)
    for lic in qs:
        yield [lic.number, lic.licensee.name, lic.licensee.email, lic.parish.name, lic.wmu.name if lic.wmu_id else "", lic.water_source, lic.source_name,
               lic.purpose, lic.daily_volume_granted_m3, lic.issued_on.isoformat(), lic.expires_on.isoformat(), lic.status]


def finance_abstraction_rows(period_start, period_end):
    """Rows for the abstraction-vs-licence export over a period (approved returns only)."""
    qs = (AbstractionRecord.objects.approved().filter(period_start__gte=period_start, period_end__lte=period_end)
          .select_related("licence__licensee", "licence__parish").order_by("licence__number", "period_start"))
    for r in qs:
        days = max((r.period_end - r.period_start).total_seconds() / 86400, 1)
        yield [r.licence.number if r.licence_id else "", r.licence.licensee.name if r.licence_id else "", r.licence.parish.name if r.licence_id else "",
               r.period_start.date().isoformat(), r.period_end.date().isoformat(), round(days, 2), r.daily_volume_granted_m3,
               r.abstraction_volume_m3, round(float(r.abstraction_volume_m3) / days, 3), r.over_limit, r.over_limit_pct or ""]
