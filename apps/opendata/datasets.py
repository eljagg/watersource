"""Open datasets: public, approved records only, with no personal data and public-supply coordinates coarsened.

Each dataset is a small class with a slug, a description, a field list and a
``rows()`` generator; spatial datasets also provide ``geojson()``. The views
turn these into preview tables, CSV downloads and GeoJSON. Nothing here reads
``classification != 'public'`` or ``approval_state != 'approved'`` records, and
licensee particulars never appear (``apps.core.restrict``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.contrib.gis.geos import Point
from django.db.models import Avg, Count, Max, Min
from django.db.models.functions import TruncMonth

from apps.core.restrict import coarsen
from apps.lic.models import Licence
from apps.lic.services import wmu_balance
from apps.obs.models import StationReading, WaterQualitySample, WellWaterLevel
from apps.ref.models import SRID, WMU, Spring, StreamflowStation, Well

PUBLIC = {"approval_state": "approved", "classification": "public"}


def _lonlat(easting, northing, public_supply: bool):
    """WGS 84 longitude/latitude from grid coordinates, coarsened for public-supply sources."""
    if easting is None or northing is None:
        return None, None
    e, n = (coarsen(easting), coarsen(northing)) if public_supply else (easting, northing)
    p = Point(float(e), float(n), srid=SRID)
    p.transform(4326)
    return round(p.x, 5), round(p.y, 5)


@dataclass
class Field:
    """One column of a dataset."""

    name: str
    description: str


class Dataset:
    """Base dataset."""

    slug = ""
    title = ""
    description = ""
    owner = ""
    fields: list[Field] = []
    spatial = False

    def rows(self):  # pragma: no cover - abstract
        """Yield dicts keyed by field name."""
        raise NotImplementedError

    def updated(self) -> date | None:
        """Date of the newest record, when the dataset can say."""
        return None

    def count(self) -> int:
        """Number of rows (computed; datasets are small enough to count)."""
        return sum(1 for _ in self.rows())

    def geojson(self):
        """FeatureCollection for spatial datasets (``lon``/``lat`` columns become the geometry)."""
        feats = []
        for r in self.rows():
            if r.get("lon") is None:
                continue
            props = {k: v for k, v in r.items() if k not in ("lon", "lat")}
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}, "properties": props})
        return {"type": "FeatureCollection", "features": feats}


class Sites(Dataset):
    """Monitoring sites."""

    slug = "monitoring-sites"
    title = "Monitoring sites — wells, streamflow stations and springs"
    description = ("Every public monitoring site WRA maintains, with its parish, basin and water management unit. Positions of public-supply "
                   "sources are rounded to a 1 km grid; all other positions are exact.")
    owner = "Resource Monitoring Unit"
    spatial = True
    fields = [Field("site_type", "well, station or spring"), Field("name", "Site name"), Field("parish", "Parish"), Field("basin", "Hydrological basin"),
              Field("wmu", "Water management unit"), Field("use", "Principal use (wells)"), Field("river", "River (stations)"),
              Field("public_supply", "true when the site serves public water supply (position rounded)"), Field("lon", "Longitude, WGS 84"), Field("lat", "Latitude, WGS 84")]

    def rows(self):
        """Yield rows."""
        for w in Well.objects.filter(is_abandoned=False, **PUBLIC).select_related("parish", "basin", "wmu").order_by("name"):
            lon, lat = _lonlat(w.easting, w.northing, w.is_public_supply)
            yield {"site_type": "well", "name": w.name, "parish": w.parish.name if w.parish_id else "", "basin": w.basin.name if w.basin_id else "",
                   "wmu": w.wmu.name if w.wmu_id else "", "use": w.get_use_display() if w.use else "", "river": "", "public_supply": w.is_public_supply, "lon": lon, "lat": lat}
        for s in StreamflowStation.objects.filter(is_active=True, **PUBLIC).select_related("parish", "river").order_by("name"):
            lon, lat = _lonlat(s.easting, s.northing, s.is_public_supply)
            yield {"site_type": "station", "name": s.name, "parish": s.parish.name if s.parish_id else "", "basin": "", "wmu": "", "use": "",
                   "river": s.river.name if s.river_id else "", "public_supply": s.is_public_supply, "lon": lon, "lat": lat}
        for s in Spring.objects.filter(**PUBLIC).select_related("parish").order_by("name"):
            lon = lat = None
            if s.location is not None:
                p = s.location.clone()
                p.transform(4326)
                lon, lat = round(p.x, 5), round(p.y, 5)
            yield {"site_type": "spring", "name": s.name, "parish": s.parish.name if s.parish_id else "", "basin": "", "wmu": "", "use": "", "river": "",
                   "public_supply": False, "lon": lon, "lat": lat}


class GroundwaterLevels(Dataset):
    """Monthly groundwater levels."""

    slug = "groundwater-levels-monthly"
    title = "Groundwater levels — monthly summary by well"
    description = "Monthly mean, minimum and maximum water level (metres below reference point) for each public well, from approved readings."
    owner = "Resource Monitoring Unit"
    fields = [Field("well", "Well name"), Field("month", "Calendar month (YYYY-MM)"), Field("readings", "Approved readings in the month"),
              Field("mean_level_m", "Mean water level, m"), Field("min_level_m", "Shallowest, m"), Field("max_level_m", "Deepest, m")]

    def _qs(self):
        """Monthly aggregate query."""
        return (WellWaterLevel.objects.filter(well__classification="public", well__approval_state="approved", **PUBLIC)
                .annotate(month=TruncMonth("measured_at")).values("well__name", "month")
                .annotate(n=Count("id"), mean=Avg("water_level_m"), lo=Min("water_level_m"), hi=Max("water_level_m")).order_by("well__name", "month"))

    def rows(self):
        """Yield rows."""
        for r in self._qs():
            yield {"well": r["well__name"], "month": r["month"].strftime("%Y-%m"), "readings": r["n"], "mean_level_m": round(float(r["mean"]), 3),
                   "min_level_m": float(r["lo"]), "max_level_m": float(r["hi"])}

    def updated(self):
        """Newest record date."""
        d = WellWaterLevel.objects.filter(**PUBLIC).aggregate(m=Max("measured_at"))["m"]
        return d.date() if d else None


class Streamflow(Dataset):
    """Monthly streamflow."""

    slug = "streamflow-monthly"
    title = "Streamflow — monthly mean discharge by station"
    description = "Monthly mean, minimum and maximum discharge (cubic metres per second) at each public gauging station, from approved readings."
    owner = "Resource Monitoring Unit"
    fields = [Field("station", "Station name"), Field("month", "Calendar month (YYYY-MM)"), Field("readings", "Approved readings in the month"),
              Field("mean_discharge_m3_s", "Mean discharge, m³/s"), Field("min_discharge_m3_s", "Lowest, m³/s"), Field("max_discharge_m3_s", "Highest, m³/s")]

    def rows(self):
        """Yield rows."""
        qs = (StationReading.objects.filter(discharge_m3_s__isnull=False, station__classification="public", station__approval_state="approved", **PUBLIC)
              .annotate(month=TruncMonth("read_at")).values("station__name", "month")
              .annotate(n=Count("id"), mean=Avg("discharge_m3_s"), lo=Min("discharge_m3_s"), hi=Max("discharge_m3_s")).order_by("station__name", "month"))
        for r in qs:
            yield {"station": r["station__name"], "month": r["month"].strftime("%Y-%m"), "readings": r["n"],
                   "mean_discharge_m3_s": round(float(r["mean"]), 4), "min_discharge_m3_s": float(r["lo"]), "max_discharge_m3_s": float(r["hi"])}

    def updated(self):
        """Newest record date."""
        d = StationReading.objects.filter(**PUBLIC).aggregate(m=Max("read_at"))["m"]
        return d.date() if d else None


class WaterQuality(Dataset):
    """Water-quality samples."""

    slug = "water-quality"
    title = "Water quality — approved sample results"
    description = "Field and laboratory results for public sampling sites: pH, conductivity, temperature, chloride, nitrate, total dissolved solids and hardness."
    owner = "Resource Monitoring Unit"
    fields = [Field("site_type", "well, spring or station"), Field("site", "Site name"), Field("sampled_on", "Sample date"), Field("ph", "pH"),
              Field("conductivity_us_cm", "Specific conductivity, µS/cm"), Field("temperature_c", "Temperature, °C"), Field("chloride_mg_l", "Chloride, mg/L"),
              Field("nitrate_mg_l", "Nitrate, mg/L"), Field("tds_mg_l", "Total dissolved solids, mg/L"), Field("hardness_mg_l", "Hardness, mg/L as CaCO₃")]

    def rows(self):
        """Yield rows."""
        qs = WaterQualitySample.objects.filter(**PUBLIC).select_related("well", "spring", "station").order_by("-sampled_at")
        for s in qs:
            site = s.well or s.spring or s.station
            if site is None or getattr(site, "classification", "public") != "public":
                continue
            f = lambda v: None if v is None else float(v)  # noqa: E731
            yield {"site_type": s.source_type, "site": site.name, "sampled_on": s.sampled_at.date().isoformat(), "ph": f(s.ph),
                   "conductivity_us_cm": f(s.specific_conductivity_us_cm), "temperature_c": f(s.temperature_c), "chloride_mg_l": f(s.chloride_mg_l),
                   "nitrate_mg_l": f(s.nitrate_mg_l), "tds_mg_l": f(s.total_dissolved_solids_mg_l), "hardness_mg_l": f(s.hardness_mg_l)}

    def updated(self):
        """Newest record date."""
        d = WaterQualitySample.objects.filter(**PUBLIC).aggregate(m=Max("sampled_at"))["m"]
        return d.date() if d else None


class LicenceRegister(Dataset):
    """Public licence register."""

    slug = "licence-register"
    title = "Water abstraction licence register"
    description = ("Licences in force and recently expired: number, source type and name, parish, water management unit, daily volume granted, dates and status. "
                   "Licensee names and contact details are not published.")
    owner = "Permits & Licences Unit"
    fields = [Field("licence_number", "Licence number"), Field("status", "active, expired, revoked or surrendered"), Field("water_source", "well or river"),
              Field("source_name", "Named source"), Field("parish", "Parish"), Field("wmu", "Water management unit"), Field("daily_volume_m3", "Daily volume granted, m³"),
              Field("issued_on", "Issue date"), Field("expires_on", "Expiry date")]

    def rows(self):
        """Yield rows."""
        for lic in Licence.objects.select_related("parish", "wmu", "well").order_by("-issued_on"):
            wmu = lic.wmu or (lic.well.wmu if lic.well_id and lic.well.wmu_id else None)
            yield {"licence_number": lic.number, "status": lic.status, "water_source": lic.water_source, "source_name": lic.source_name, "parish": lic.parish.name,
                   "wmu": wmu.name if wmu else "", "daily_volume_m3": float(lic.daily_volume_granted_m3), "issued_on": lic.issued_on.isoformat(),
                   "expires_on": lic.expires_on.isoformat()}

    def updated(self):
        """Newest record date."""
        return Licence.objects.aggregate(m=Max("issued_on"))["m"]


class WMUBalance(Dataset):
    """WMU balance sheet."""

    slug = "wmu-balance"
    title = "Water management units — safe yield and licensed allocation"
    description = "For each water management unit: safe yield, total daily volume licensed, applications pending, and utilisation as a percentage of safe yield."
    owner = "Planning & Investigation Unit"
    fields = [Field("wmu_code", "WMU code"), Field("wmu", "WMU name"), Field("basin", "Basin"), Field("safe_yield_m3_d", "Safe yield, m³/day"),
              Field("licensed_m3_d", "Licensed daily volume, m³/day"), Field("pending_m3_d", "Requested in pending applications, m³/day"),
              Field("licences", "Active licences"), Field("utilisation_pct", "Licensed ÷ safe yield, %"), Field("safe_yield_source", "Where the safe-yield figure comes from")]

    def rows(self):
        """Yield rows."""
        for w in WMU.objects.select_related("basin").order_by("code"):
            b = wmu_balance(w)
            yield {"wmu_code": w.code, "wmu": w.name, "basin": w.basin.name if w.basin_id else "",
                   "safe_yield_m3_d": float(b["safe_yield"]) if b["safe_yield"] is not None else None, "licensed_m3_d": float(b["allocated"]),
                   "pending_m3_d": float(b["pending"]), "licences": b["licences"], "utilisation_pct": b["utilisation_pct"], "safe_yield_source": w.safe_yield_source or ""}


DATASETS = {d.slug: d for d in (Sites(), GroundwaterLevels(), Streamflow(), WaterQuality(), LicenceRegister(), WMUBalance())}
