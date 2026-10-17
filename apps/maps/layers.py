"""GeoJSON layers for the maps (v0.7.0): boundaries, WMU balance and sites.

Everything is served in WGS 84 (EPSG:4326) for Leaflet; storage stays JAD2001.
Site coordinates go through :func:`apps.core.restrict.mask_site`, so a
public-supply source is coarsened for anyone outside the restricted-data roles,
exactly as in the API and the exports. Licensee particulars never appear.
"""
from __future__ import annotations

import json
import re

from django.contrib.gis.geos import Point
from django.db import models

from apps.core.restrict import can_see_restricted, mask_site
from apps.lic.services import wmu_balance
from apps.maps.models import WraFeature
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
        sources.add(re.sub(r"\s*\([^)]*\)$", "", o.geom_source or "unknown"))  # one entry per source, not per feature
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


# -- WRA reference layers (v0.11.0, apps.maps.models.WraFeature) ------------------------------------
HYDROSTRAT_CLASSES = ("Limestone Aquifer", "Limestone Aquiclude", "Alluvium Aquifer", "Alluvium Aquiclude", "Coastal Aquifer", "Coastal Aquiclude", "Basal Aquiclude",
                      "Swamp/Marsh/Mangrove", "Water Body")


def _wra_layer(layer, props, simplify=SIMPLIFY_M):
    feats = []
    source = None
    for o in WraFeature.objects.filter(layer=layer):
        g = o.geom.simplify(simplify, preserve_topology=True) if simplify and o.geom.geom_type != "Point" else o.geom.clone()
        g.transform(EXPORT_SRID)
        source = o.source
        feats.append({"type": "Feature", "id": o.feature_id, "geometry": json.loads(g.json), "properties": {"name": o.name, "source": o.source, **props(o)}})
    return _fc(feats, sources=[source] if source else [])


def rivers():
    """WRA rivers and waterways (digitised from the 1:50,000 sheets)."""
    return _wra_layer("rivers", lambda o: {}, simplify=25)


def gauges():
    """WRA stream gauging stations with their station code, WMU and drainage area."""
    def props(o):
        p = {k.lower(): v for k, v in o.props.items()}
        return {"code": o.feature_id, "wmu": p.get("wmu"), "basin": p.get("hydrobasin"), "state": p.get("state"), "type": p.get("type"),
                "drainage_km2": p.get("dr_area_km"), "elevation_m": p.get("elevatn_m"), "established": p.get("date_est")}
    return _wra_layer("gauges", props, simplify=0)


def subwmus():
    """WRA sub-WMUs."""
    return _wra_layer("subwmus", lambda o: {})


def hydrostrat():
    """WRA hydrostratigraphy 2018: aquifer and aquiclude units."""
    return _wra_layer("hydrostrat", lambda o: {"unit": o.name or "Unclassified"})


def floodplains():
    """100-year floodplains from WRA's flood studies (Upper Morass, Coleburn Gully, Hope River, Rio Cobre, Rio Grande, Rio Minho)."""
    return _wra_layer("floodplains", lambda o: {"study": o.props.get("study"), "rp": o.props.get("RP"), "area_km2": o.props.get("Area_km2") or o.props.get("AreaSqKm")},
                      simplify=20)


def melissa():
    """Areas WRA mapped as flooded after Hurricane Melissa."""
    def props(o):
        p = {k.lower(): v for k, v in o.props.items()}
        return {"parish": p.get("parish"), "wmu": p.get("wmu"), "captured": p.get("captured"), "flood_type": p.get("flood_type"), "area_km2": p.get("area_sq_km"),
                "remarks": p.get("remarks") or p.get("descr")}
    return _wra_layer("melissa", props, simplify=20)


def wmu_detail(wmu, user) -> dict:
    """Everything the map's WMU panel shows (v0.12.0): balance figures, a 12-month reported-abstraction series, site counts and (staff) licences."""
    from datetime import datetime, time, timedelta

    from django.db.models import Sum
    from django.db.models.functions import TruncMonth
    from django.utils import timezone

    from apps.lic.models import Licence, LicenceStatus
    from apps.obs.models import AbstractionRecord

    b = wmu_balance(wmu)
    since = timezone.make_aware(datetime.combine((timezone.localdate().replace(day=1) - timedelta(days=365)).replace(day=1), time.min))
    monthly = (AbstractionRecord.objects.filter(approval_state="approved", period_start__gte=since)
               .filter(models.Q(licence__wmu=wmu) | models.Q(licence__wmu__isnull=True, well__wmu=wmu))
               .annotate(m=TruncMonth("period_start")).values("m").annotate(v=Sum("abstraction_volume_m3")).order_by("m"))
    series = [{"month": r["m"].strftime("%Y-%m"), "m3": float(r["v"] or 0)} for r in monthly]
    out = {"code": wmu.code, "name": wmu.name, "basin": wmu.basin.name if wmu.basin_id else None, "source": wmu.geom_source,
           "safe_yield": float(b["safe_yield"]) if b["safe_yield"] is not None else None, "safe_yield_source": wmu.safe_yield_source,
           "allocated": float(b["allocated"]), "pending": float(b["pending"]), "reported_avg": float(b["reported_avg"]) if b["reported_avg"] is not None else None,
           "headroom": float(b["headroom"]) if b["headroom"] is not None else None, "licences": b["licences"],
           "utilisation_pct": b["utilisation_pct"], "utilisation_with_pending_pct": b["utilisation_with_pending_pct"],
           "wells": Well.objects.filter(wmu=wmu, is_abandoned=False).count(), "stations": StreamflowStation.objects.filter(wmu=wmu, is_active=True).count(),
           "gauges": WraFeature.objects.filter(layer="gauges", geom__within=wmu.geom).count() if wmu.geom is not None else 0,
           "subwmus": list(WraFeature.objects.filter(layer="subwmus", geom__intersects=wmu.geom).values_list("name", flat=True)[:12]) if wmu.geom is not None else [],
           "abstraction_monthly": series, "licence_list": []}
    if getattr(user, "is_authenticated", False) and getattr(user, "is_staff_user", False):
        in_wmu = models.Q(wmu=wmu) | models.Q(wmu__isnull=True, well__wmu=wmu)
        out["licence_list"] = [{"number": lic.number, "volume": float(lic.daily_volume_granted_m3 or 0), "expires": lic.expires_on.isoformat() if lic.expires_on else None,
                                "url": f"/licensing/licences/{lic.pk}/"}
                               for lic in Licence.objects.filter(in_wmu, status=LicenceStatus.ACTIVE).order_by("-daily_volume_granted_m3")[:8]]
    return out


LAYERS = {"parishes": lambda user: parishes(), "basins": lambda user: basins(), "wmus": lambda user: wmus(), "aquifers": lambda user: aquifers(), "sites": sites,
          "rivers": lambda user: rivers(), "gauges": lambda user: gauges(), "subwmus": lambda user: subwmus(), "hydrostrat": lambda user: hydrostrat(),
          "floodplains": lambda user: floodplains(), "melissa": lambda user: melissa()}
#: layers identical for every viewer, cached server-side for an hour (cleared by load_wra_layers / load_boundaries)
PUBLIC_CACHED = {"rivers", "gauges", "subwmus", "hydrostrat", "parishes", "floodplains", "melissa"}
