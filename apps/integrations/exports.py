"""Public-data exports for ArcGIS Enterprise (Addendum 1 §9) and Finance (ToR H.xiii)."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib.gis.db.models.functions import Transform
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


def export_public_geojson() -> list[str]:
    """Only rows in public views (approved + public) leave the system."""
    stamp = timezone.now().strftime("%Y%m%d")
    out = _out_dir("arcgis")
    files = []
    wells = Well.objects.public().annotate(geom4326=Transform("location", 4326)).select_related("parish", "basin", "wmu")
    feats = [_feature(w, {"name": w.name, "parish": w.parish.name if w.parish_id else None, "basin": w.basin.name if w.basin_id else None,
                           "wmu": w.wmu.name if w.wmu_id else None, "elevation_m": float(w.elevation_m) if w.elevation_m is not None else None,
                           "use": w.use, "status": "abandoned" if w.is_abandoned else "in_use"}) for w in wells]
    path = out / f"wells_public_{stamp}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:4326"}}, "features": feats}))
    files.append(str(path))
    stations = StreamflowStation.objects.public().annotate(geom4326=Transform("location", 4326)).select_related("parish", "river")
    feats = [_feature(s, {"name": s.name, "river": s.river.name if s.river_id else None, "parish": s.parish.name if s.parish_id else None}) for s in stations]
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
