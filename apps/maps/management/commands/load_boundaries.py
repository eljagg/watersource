"""Load boundary polygons for parishes, basins, WMUs and aquifers (v0.7.0 maps).

Three sources, in order of authority:

1. **WRA's own files** — ``--parishes/--basins/--wmus/--aquifers <file>``: any GeoJSON
   or shapefile GDAL can read (shapefiles via ``ogr2ogr`` to GeoJSON first). Features
   match by a ``code`` property, or by ``name`` when there is no code. Geometry in any
   CRS GDAL recognises is reprojected to JAD2001 (EPSG:3448).
2. **geoBoundaries parishes** — ``data/gis/parishes.geojson`` (CC BY 4.0) loaded by
   default when a parish has no boundary yet.
3. **Demonstration stand-ins** — ``--demo-shapes`` cuts basin and WMU cells from the
   island outline with PostGIS Voronoi polygons around ``data/gis/demo_seeds.csv``.
   Only fills blanks, never overwrites a real boundary, and tags every shape it makes
   ``geom_source = "demonstration stand-in"`` so the map legend can say so.

Idempotent: safe to run on every deploy.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.ref.models import SRID, WMU, Aquifer, Basin, Parish

GIS_DIR = Path(settings.BASE_DIR) / "data" / "gis"
DEMO_SOURCE = "demonstration stand-in"
GEOBOUNDARIES_SOURCE = "geoBoundaries gbOpen JAM ADM1 (CC BY 4.0)"

#: geoBoundaries spells parishes "Saint X"; WRA's reference data uses "St. X"
NAME_ALIASES = {"Saint Andrew": "St. Andrew", "Saint Ann": "St. Ann", "Saint Catherine": "St. Catherine", "Saint Elizabeth": "St. Elizabeth",
                "Saint James": "St. James", "Saint Mary": "St. Mary", "Saint Thomas": "St. Thomas"}


def _multi(geom: GEOSGeometry) -> MultiPolygon:
    geom = geom.clone()
    if geom.srid != SRID:
        geom.transform(SRID)
    if geom.geom_type == "Polygon":
        geom = MultiPolygon(geom, srid=SRID)
    elif geom.geom_type == "GeometryCollection":
        polys = [g for g in geom if g.geom_type in ("Polygon", "MultiPolygon")]
        flat = []
        for g in polys:
            flat.extend(list(g) if g.geom_type == "MultiPolygon" else [g])
        geom = MultiPolygon(flat, srid=SRID)
    return geom


class Command(BaseCommand):
    """Boundary loader (see module docstring)."""

    help = "Load parish/basin/WMU/aquifer boundaries from WRA files, geoBoundaries (parishes) or demonstration stand-ins."

    def add_arguments(self, parser):
        """One file option per layer, plus --demo-shapes/--force."""
        for layer in ("parishes", "basins", "wmus", "aquifers"):
            parser.add_argument(f"--{layer}", help=f"GeoJSON file of {layer} with a 'code' (or 'name') property; replaces existing boundaries.")
        parser.add_argument("--demo-shapes", action="store_true", help="Build Voronoi stand-in shapes for basins and WMUs that have no boundary.")
        parser.add_argument("--force", action="store_true", help="With --demo-shapes: rebuild stand-ins even where one exists (never touches real boundaries).")

    def handle(self, *args, **opts):
        """Files first, then geoBoundaries parishes for blanks, then demonstration stand-ins if asked."""
        models = {"parishes": Parish, "basins": Basin, "wmus": WMU, "aquifers": Aquifer}
        for layer, model in models.items():
            if opts.get(layer):
                n = self._load_file(model, Path(opts[layer]), source=f"WRA file {Path(opts[layer]).name}")
                self.stdout.write(f"{layer:9s} {n} boundaries loaded from {opts[layer]}")
        if not opts.get("parishes") and Parish.objects.filter(geom__isnull=True).exists():
            n = self._load_file(Parish, GIS_DIR / "parishes.geojson", source=GEOBOUNDARIES_SOURCE, only_missing=True)
            self.stdout.write(f"parishes  {n} boundaries loaded from geoBoundaries")
        if opts["demo_shapes"]:
            self._demo_shapes(force=opts["force"])

    # -- files -----------------------------------------------------------------------------
    def _load_file(self, model, path: Path, source: str, only_missing: bool = False) -> int:
        if not path.exists():
            raise CommandError(f"{path} not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        feats = data.get("features", [])
        by_code = {o.code: o for o in model.objects.all()}
        by_name = {o.name.lower(): o for o in model.objects.all()}
        n = 0
        for f in feats:
            props = {k.lower(): v for k, v in (f.get("properties") or {}).items()}
            name = props.get("name") or props.get("shapename") or ""
            obj = by_code.get(props.get("code")) or by_name.get(NAME_ALIASES.get(name, name).lower())
            if obj is None:
                self.stdout.write(f"  skipped feature without a matching {model._meta.verbose_name}: code={props.get('code')!r} name={name!r}")
                continue
            if only_missing and obj.geom is not None:
                continue
            geom = GEOSGeometry(json.dumps(f["geometry"]), srid=4326)
            obj.geom, obj.geom_source = _multi(geom), source
            obj.save(update_fields=["geom", "geom_source"])
            n += 1
        return n

    # -- demonstration stand-ins -------------------------------------------------------------
    def _seeds(self):
        seeds = {"basin": {}, "wmu": {}}
        with open(GIS_DIR / "demo_seeds.csv", encoding="utf-8") as fh:
            for row in csv.DictReader(line for line in fh if not line.startswith("#")):
                p = Point(float(row["lon"]), float(row["lat"]), srid=4326)
                p.transform(SRID)
                seeds[row["layer"]][row["code"]] = p
        return seeds

    def _voronoi(self, points: dict[str, Point], clip: GEOSGeometry) -> dict[str, MultiPolygon]:
        """Voronoi cell of each seed point, clipped to ``clip``; computed by PostGIS."""
        if not points:
            return {}
        if len(points) == 1:
            return {next(iter(points)): _multi(clip)}
        wkt = "MULTIPOINT(" + ", ".join(f"({p.x} {p.y})" for p in points.values()) + ")"
        with connection.cursor() as cur:
            cur.execute("SELECT ST_AsEWKT(ST_VoronoiPolygons(ST_GeomFromText(%s, %s), 0, ST_Envelope(ST_Buffer(ST_GeomFromEWKT(%s), 20000))))",
                        [wkt, SRID, clip.ewkt])
            cells = GEOSGeometry(cur.fetchone()[0])
        out = {}
        for cell in cells:
            for code, p in points.items():
                if cell.contains(p):
                    piece = cell.intersection(clip)
                    if not piece.empty:
                        out[code] = _multi(piece)
        return out

    def _demo_shapes(self, force: bool):
        island_parts = [p.geom for p in Parish.objects.exclude(geom__isnull=True)]
        if not island_parts:
            raise CommandError("No parish boundaries loaded; cannot build demonstration shapes.")
        island = island_parts[0]
        for g in island_parts[1:]:
            island = island.union(g)
        island = island.buffer(0)
        seeds = self._seeds()
        basins = {b.code: b for b in Basin.objects.all()}
        cells = self._voronoi({c: p for c, p in seeds["basin"].items() if c in basins}, island)
        made = 0
        for code, geom in cells.items():
            b = basins[code]
            if b.geom is None or (force and b.geom_source == DEMO_SOURCE):
                b.geom, b.geom_source = geom, DEMO_SOURCE
                b.save(update_fields=["geom", "geom_source"])
                made += 1
        self.stdout.write(f"basins    {made} demonstration shapes")
        made = 0
        for b in Basin.objects.exclude(geom__isnull=True):
            wmus = {w.code: w for w in b.wmus.all()}
            cells = self._voronoi({c: p for c, p in seeds["wmu"].items() if c in wmus}, b.geom)
            for code, geom in cells.items():
                w = wmus[code]
                if w.geom is None or (force and w.geom_source == DEMO_SOURCE):
                    w.geom, w.geom_source = geom, DEMO_SOURCE
                    w.save(update_fields=["geom", "geom_source"])
                    made += 1
        self.stdout.write(f"wmus      {made} demonstration shapes")
