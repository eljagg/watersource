"""Load WRA's real boundaries and reference layers from the Government of Jamaica ArcGIS Online (v0.11.0).

    manage.py load_wra_layers                      # every layer, over the network
    manage.py load_wra_layers --layers basins,wmus
    manage.py load_wra_layers --from-dir data/gis/wra   # <layer>.geojson files saved earlier (tests, offline)

Basins and WMUs are matched to our reference rows by name (WMUs WRA lists
that we do not have yet are created, under their basin). Real boundaries
replace demonstration stand-ins and geoBoundaries shapes; a boundary loaded
from a file WRA handed us directly (``load_boundaries --wmus file``) is kept.
Rivers, gauging stations, sub-WMUs and the 2018 hydrostratigraphy go into
:class:`apps.maps.models.WraFeature`.

Network trouble is reported and the command exits normally, so a deploy
without internet access still starts; the demonstration stand-ins then fill
whatever is missing.
"""
from __future__ import annotations

import json
import re
import urllib.error
from datetime import timedelta
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.maps import wra_arcgis
from apps.maps.models import WraFeature, WraLayer, WraSync
from apps.ref.models import SRID, WMU, Basin

#: WRA's WMU names → the names in data/reference/wmus.csv where they differ
WMU_ALIASES = {"wagwater river": "Wag Water River", "rio bueno - white river": "Rio Bueno", "martha brae": "Martha Brae River"}
KEEP_SOURCE_PREFIX = "WRA file"  # a shapefile WRA handed us directly beats the online copy


def _multi(geom):
    if geom.geom_type == "Polygon":
        geom = MultiPolygon(geom, srid=geom.srid)
    if not geom.valid:
        geom = geom.buffer(0)
        if geom.geom_type == "Polygon":
            geom = MultiPolygon(geom, srid=geom.srid)
    return geom


def _geom(feature):
    g = feature.get("geometry")
    if not g:
        return None
    geom = GEOSGeometry(json.dumps(g), srid=4326)
    geom.transform(SRID)
    return geom


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


class Command(BaseCommand):
    """Copy WRA's published layers into the database."""

    help = __doc__

    def add_arguments(self, parser):
        """--layers, --from-dir, --timeout."""
        parser.add_argument("--layers", default=",".join(wra_arcgis.SERVICES), help="Comma-separated subset of: " + ", ".join(wra_arcgis.SERVICES))
        parser.add_argument("--from-dir", help="Directory of <layer>.geojson files instead of the network (as saved by --save-dir).")
        parser.add_argument("--save-dir", help="Also save each fetched layer as <layer>.geojson here.")
        parser.add_argument("--timeout", type=int, default=90)
        parser.add_argument("--max-age-days", type=int, default=7, help="Skip a layer fetched successfully within this many days (0 = always fetch).")

    def handle(self, *args, **opts):
        """Fetch each requested layer and load it; never raise on network trouble."""
        wanted = [s.strip() for s in opts["layers"].split(",") if s.strip()]
        unknown = [w for w in wanted if w not in wra_arcgis.SERVICES]
        if unknown:
            self.stderr.write(f"unknown layer(s): {', '.join(unknown)}")
            return
        fresh = {s.layer: s for s in WraSync.objects.filter(ok=True, fetched_at__gte=timezone.now() - timedelta(days=opts["max_age_days"]))} if opts["max_age_days"] else {}
        for name in wanted:
            if name in fresh and not opts.get("from_dir"):
                self.stdout.write(f"{name:10s} up to date ({fresh[name].count} features, fetched {fresh[name].fetched_at:%d %b %H:%M}); skipped")
                continue
            try:
                feats = self._features(name, opts)
            except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                self.stderr.write(f"{name:10s} not loaded — {exc.__class__.__name__}: {exc}")
                WraSync.objects.update_or_create(layer=name, defaults={"fetched_at": timezone.now(), "ok": False, "message": f"{exc.__class__.__name__}: {exc}"[:300]})
                continue
            if opts.get("save_dir"):
                out = Path(opts["save_dir"])
                out.mkdir(parents=True, exist_ok=True)
                (out / f"{name}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
            loader = getattr(self, f"_load_{name}", None) or (lambda f, n=name: self._load_features(n, f))
            with transaction.atomic():
                msg = loader(feats)
                WraSync.objects.update_or_create(layer=name, defaults={"fetched_at": timezone.now(), "count": len(feats), "ok": True, "message": msg[:300]})
            cache.delete(f"maps.layer.{name}")
            self.stdout.write(f"{name:10s} {msg}")

    # -- fetching ------------------------------------------------------------------------------
    def _features(self, name, opts):
        if opts.get("from_dir"):
            path = Path(opts["from_dir"]) / f"{name}.geojson"
            if not path.exists():
                raise FileNotFoundError(f"{path} not found")
            return json.loads(path.read_text(encoding="utf-8")).get("features", [])
        service = wra_arcgis.SERVICES[name][0]
        return wra_arcgis.fetch(service, timeout=opts["timeout"])

    # -- basins and WMUs: into the reference tables -----------------------------------------------
    def _load_basins(self, feats):
        by_name = {_norm(b.name): b for b in Basin.objects.all()}
        n = skipped = 0
        for f in feats:
            props = f.get("properties") or {}
            name = wra_arcgis.pick(props, wra_arcgis.SERVICES["basins"][1])
            geom = _geom(f)
            if not name or geom is None:
                skipped += 1  # WRA's layer carries one blank sliver
                continue
            b = by_name.get(_norm(name))
            if b is None:
                self.stdout.write(f"  basin {name!r} is not in our reference list; skipped")
                continue
            if (b.geom_source or "").startswith(KEEP_SOURCE_PREFIX):
                continue
            b.geom, b.geom_source = _multi(geom), f"{wra_arcgis.SOURCE} (basin {wra_arcgis.pick(props, ('BasinNo',))})"
            b.save(update_fields=["geom", "geom_source"])
            n += 1
        return f"{n} basin boundaries loaded ({skipped} blank skipped)"

    def _load_wmus(self, feats):
        basins = {_norm(b.name): b for b in Basin.objects.all()}
        by_name = {_norm(w.name): w for w in WMU.objects.all()}
        n = created = skipped = 0
        for f in feats:
            props = f.get("properties") or {}
            name = wra_arcgis.pick(props, wra_arcgis.SERVICES["wmus"][1])
            geom = _geom(f)
            if not name or geom is None:
                skipped += 1
                continue
            ours = WMU_ALIASES.get(_norm(name), name)
            w = by_name.get(_norm(ours))
            basin = basins.get(_norm(wra_arcgis.pick(props, ("Hydrobasin",))))
            if w is None:
                w = WMU.objects.create(code=self._next_code(), name=name, basin=basin)
                by_name[_norm(name)] = w
                created += 1
            elif w.basin_id is None and basin is not None:
                w.basin = basin
                w.save(update_fields=["basin"])
            if (w.geom_source or "").startswith(KEEP_SOURCE_PREFIX):
                continue
            w.geom, w.geom_source = _multi(geom), f"{wra_arcgis.SOURCE} (WMU {wra_arcgis.pick(props, ('Wmu_No',))})"
            w.save(update_fields=["geom", "geom_source"])
            n += 1
        return f"{n} WMU boundaries loaded, {created} WMUs added ({skipped} blank skipped)"

    @staticmethod
    def _next_code():
        nums = [int(c[1:]) for c in WMU.objects.values_list("code", flat=True) if re.fullmatch(r"W\d+", c)]
        return f"W{(max(nums) + 1 if nums else 1):02d}"

    # -- everything else: WraFeature -----------------------------------------------------------------
    def _load_features(self, layer, feats):
        _, name_fields, id_fields = wra_arcgis.SERVICES[layer]
        now = timezone.now()
        seen = set()
        rows = []
        for i, f in enumerate(feats):
            props = f.get("properties") or {}
            geom = _geom(f)
            if geom is None:
                continue
            fid = wra_arcgis.pick(props, id_fields) or str(f.get("id") or i)
            if fid in seen:
                fid = f"{fid}-{i}"
            seen.add(fid)
            rows.append(WraFeature(layer=layer, feature_id=fid[:64], name=wra_arcgis.pick(props, name_fields)[:200],
                                   props={k: v for k, v in props.items() if v is not None and not k.lower().startswith("shape__")}, geom=geom, source=wra_arcgis.SOURCE, fetched_at=now))
        if not rows:
            return f"0 {WraLayer(layer).label.lower()} — nothing loaded, existing features kept"
        gone = WraFeature.objects.filter(layer=layer).delete()[0]
        WraFeature.objects.bulk_create(rows, batch_size=500)
        return f"{len(rows)} {WraLayer(layer).label.lower()} loaded ({gone} replaced)"
