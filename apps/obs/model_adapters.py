"""Adapters that turn model output files into rows of the ``model_output`` category (design doc 15 §3.1).

Each adapter yields plain dicts with the category's column names so the file goes
through exactly the same validation, review and promotion path as any other
submission. Supported today:

* ``swatplus`` — SWAT+ ``channel_sd_day.txt`` (daily channel output, revision 60+):
  whitespace-delimited, two header lines (titles, units), columns ``jday mon day yr
  unit gis_id name … flo_out …``. Each ``unit`` (channel number) becomes a
  ``reach`` row; ``flo_out`` (m³/s) is the discharge variable.
* ``wflow`` — Wflow.jl ``[output.csv]`` file: first column ``time`` (ISO date), one
  column per gauge in the form ``Q_<gauge-id>`` or any name you map with
  ``--map``; values are river discharge in m³/s.
* ``generic`` — a CSV already in the category's own column layout (the template
  downloadable from the Data submissions page).

Mapping model element ids to WaterSource stations is given with ``--map
"12=Bog Walk,7=Flat Bridge"``; unmapped elements are kept as ``reach`` rows with
``feature_ref`` set, so nothing is lost.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime


def parse_map(spec: str) -> dict[str, str]:
    """``"12=Bog Walk,7=Flat Bridge"`` → ``{"12": "Bog Walk", "7": "Flat Bridge"}``."""
    out = {}
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _row(run: str, feature_ref: str, when: str, value, *, station: str = "", variable: str = "discharge_m3_s", unit: str = "m3/s") -> dict:
    return {
        "run": run, "feature_type": "station" if station else "reach", "station": station, "well": "",
        "feature_ref": feature_ref, "variable": variable, "observed_at": when, "value": str(value), "unit": unit, "remarks": "",
    }


def swatplus_channel_rows(text: str, run: str, station_map: dict[str, str] | None = None, variable_column: str = "flo_out"):
    """Rows from a SWAT+ ``channel_sd_day.txt`` (or ``channel_sd_mon.txt``) file."""
    station_map = station_map or {}
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # line 0 = title, line 1 = column names, line 2 = units (both headers are present from rev. 60)
    header_idx = next(i for i, ln in enumerate(lines) if ln.split()[:2] == ["jday", "mon"])
    cols = lines[header_idx].split()
    body = lines[header_idx + 1:]
    if body and not body[0].split()[0].isdigit():
        body = body[1:]  # units line
    ci = {c: i for i, c in enumerate(cols)}
    for ln in body:
        parts = ln.split()
        if len(parts) < len(cols):
            continue
        unit_id = parts[ci["unit"]]
        when = datetime(int(parts[ci["yr"]]), int(parts[ci["mon"]]), int(parts[ci["day"]])).strftime("%Y-%m-%dT00:00:00")
        yield _row(run, f"channel {unit_id}", when, parts[ci[variable_column]], station=station_map.get(unit_id, ""))


def wflow_csv_rows(text: str, run: str, station_map: dict[str, str] | None = None):
    """Rows from a Wflow.jl scalar CSV output (``time`` column + one column per gauge)."""
    station_map = station_map or {}
    reader = csv.DictReader(io.StringIO(text))
    gauge_cols = [c for c in reader.fieldnames or [] if c != "time"]
    for rec in reader:
        when = rec["time"].strip()
        if len(when) == 10:
            when += "T00:00:00"
        for col in gauge_cols:
            v = (rec.get(col) or "").strip()
            if v in ("", "NaN", "nan", "missing"):
                continue
            gauge_id = col.split("_", 1)[1] if "_" in col else col
            yield _row(run, f"gauge {gauge_id}", when, v, station=station_map.get(gauge_id, station_map.get(col, "")))


def generic_rows(text: str, run: str = ""):
    """Rows from a CSV already in the category layout; fills ``run`` when the column is empty."""
    for rec in csv.DictReader(io.StringIO(text)):
        if run and not (rec.get("run") or "").strip():
            rec["run"] = run
        yield rec


ADAPTERS = {"swatplus": swatplus_channel_rows, "wflow": wflow_csv_rows, "generic": generic_rows}
