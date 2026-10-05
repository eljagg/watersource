"""Field-level restriction for public-supply sources and licensee particulars (Methodology §4A, ADR-0002).

A public-supply well or station can still be *listed* publicly (name, parish,
basin, status), but its exact coordinates and engineering details are
restricted by default: guests, clients, the public views, the API and the
exports see coordinates coarsened to :data:`COORDINATE_GRID_M` and no
lithology, casing, pump-test, reference-point or instrument detail. Licensee
particulars (name, address, contact) never appear outside staff pages.

WRA changes the flag per record in the admin console; the change is audited
by ``ref.Well.save`` / ``ref.StreamflowStation.save``.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings

#: Grid, in metres, that public coordinates of public-supply sources are snapped to.
COORDINATE_GRID_M = int(getattr(settings, "WATERSOURCE", {}).get("PUBLIC_COORDINATE_GRID_M", 1000))


def can_see_restricted(user) -> bool:
    """True for signed-in staff holding a role in ``roles.RESTRICTED_DATA_ROLES`` (or superusers)."""
    from apps.accounts import roles

    return bool(user is not None and getattr(user, "is_authenticated", False) and user.has_role(*roles.RESTRICTED_DATA_ROLES))


def coarsen(value, grid: int = COORDINATE_GRID_M):
    """Snap a grid coordinate to the centre of its ``grid``-metre cell; ``None`` stays ``None``."""
    if value is None:
        return None
    v = Decimal(value)
    cell = (v // grid) * grid
    return cell + Decimal(grid) / 2


def mask_site(site, user) -> dict:
    """Coordinates/elevation of ``site`` as the caller may see them.

    Returns a dict with ``easting``, ``northing``, ``elevation_m`` and
    ``coordinates_coarsened`` (bool). Exact values for non-public-supply
    sites and for restricted-data roles; coarsened otherwise.
    """
    if not getattr(site, "is_public_supply", False) or can_see_restricted(user):
        return {"easting": site.easting, "northing": site.northing, "elevation_m": site.elevation_m, "coordinates_coarsened": False}
    return {"easting": coarsen(site.easting), "northing": coarsen(site.northing), "elevation_m": None, "coordinates_coarsened": True}
