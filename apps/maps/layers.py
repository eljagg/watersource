"""GeoJSON layers for the maps (v0.7.0): boundaries, WMU balance and sites.

Everything is served in WGS 84 (EPSG:4326) for Leaflet; storage stays JAD2001.
Site coordinates go through :func:`apps.core.restrict.mask_site`, so a
public-supply source is coarsened for anyone outside the restricted-data roles,
exactly as in the API and the exports. Licensee particulars never appear.
"""
from __future__ import annotations

import json

from django.contrib.gis.geos import Point

from apps.core.restrict import can_see_restricted, mask_site
from apps.lic.services import wmu_balance
from apps.ref.models import SRID, WMU, Aquifer, Basin, Parish, Spring, StreamflowStation, Well

EXPORT_SRID = 4326
SIMPLIFY_M = 60  # metres; keeps the parish layer ~150 kB instead of 450 kB


def _geom_json(geom):
    if geom is None:
        return None
    g = geom.simplify(SIMPLIFY_M, preserve_topology=True) if geom.geom_type.endswith("Polygon") else geom.clone()
    g.transform(EXPORT_SRID)
    return json.loads(g.json)


def _fc(features, **extra):
    return {"type": "FeatureCollection", "features": features, **extra}


def _boundary_layer(qs, props):
    feats = []
    sources = set()
    for o in qs:
        if o.geom is None:
            continue
        sources.add(o.geom_source or "unknown")
        feats.append({"type": "Feature", "id": o.code, "geometry": _geom_json(o.geom), "properties": props(o)})
    return _fc(feats, sources=sorted(sources))


def parishes():
    """Parish boundaries."""
    return _boundary_layer(Parish.objects.all(), lambda o: {"code": o.code, "name": o.name, "source": o.geom_source})


def basins():
    """Basin boundaries with WMU counts."""
    return _boundary_layer(Basin.objects.all(), lambda o: {"code": o.code, "name": o.name, "source": o.geom_source, "wmus": o.wmus.count()})


def aquifers():
    """Aquifer boundaries with type and safe yield."""
    return _boundary_layer(Aquifer.objects.select_related("basin"),
                           lambda o: {"code": o.code, "name": o.name, "source": o.geom_source, "type": o.get_aquifer_type_display(), "basin": o.basin.name if o.basin_id else None,
                                      "safe_yield_m3_d": float(o.safe_yield_m3_d) if o.safe_yield_m3_d is not None else None})


def wmus():
    """WMU polygons carrying the balance-sheet figures, so the map can colour by utilisation."""
    def props(o):
        b = wmu_balance(o)
        return {"code": o.code, "name": o.name, "basin": o.basin.name if o.basin_id else None, "source": o.geom_source,
                "safe_yield": float(b["safe_yield"]) if b["safe_yield"] is not None else None, "allocated": float(b["allocated"]), "pending": float(b["pending"]),
                "licences": b["licences"], "utilisation_pct": b["utilisation_pct"], "utilisation_with_pending_pct": b["utilisation_with_pending_pct"],
                "headroom": float(b["headroom"]) if b["headroom"] is not None else None}
    return _boundary_layer(WMU.objects.select_related("basin"), props)


def _site_feature(site, kind, user, props_fn):
    if hasattr(site, "easting"):
        m = mask_site(site, user)
        if m["easting"] is None or m["northing"] is None:
            return None
        p = Point(float(m["easting"]), float(m["northing"]), srid=SRID)
    else:  # springs carry only a location point and are never public-supply restricted
        if site.location is None:
            return None
        m = {"coordinates_coarsened": False}
        p = site.location.clone()
    p.transform(EXPORT_SRID)
    props = {"kind": kind, "name": site.name, "parish": site.parish.name if getattr(site, "parish_id", None) else None,
             "public_supply": bool(getattr(site, "is_public_supply", False)), "coordinates_coarsened": m["coordinates_coarsened"], **props_fn(site)}
    return {"type": "Feature", "id": f"{kind}-{site.pk}", "geometry": {"type": "Point", "coordinates": [round(p.x, 5), round(p.y, 5)]}, "properties": props}


def sites(user):
    """Wells, streamflow stations and springs as points (masked per viewer)."""
    feats = []
    for w in Well.objects.filter(is_abandoned=False).select_related("parish", "wmu", "basin"):
        f = _site_feature(w, "well", user, lambda o: {"use": o.get_use_display() if o.use else None, "wmu": o.wmu.name if o.wmu_id else None,
                                                      "basin": o.basin.name if o.basin_id else None})
        if f:
            feats.append(f)
    for s in StreamflowStation.objects.filter(is_active=True).select_related("parish", "river"):
        f = _site_feature(s, "station", user, lambda o: {"river": o.river.name if o.river_id else None})
        if f:
            feats.append(f)
    for s in Spring.objects.select_related("parish"):
        f = _site_feature(s, "spring", user, lambda o: {})
        if f:
            feats.append(f)
    return _fc(feats, exact_coordinates=can_see_restricted(user))


LAYERS = {"parishes": lambda user: parishes(), "basins": lambda user: basins(), "wmus": lambda user: wmus(), "aquifers": lambda user: aquifers(), "sites": sites}
