"""Hydro GeoAnalyst (SQL Server) read-only extraction via ODBC (ToR §E.2).
Requires the Microsoft ODBC Driver 18 in the container image and a read-only
SQL login on the HGA server. Table/column names are confirmed in profiling."""
from __future__ import annotations

from django.conf import settings


def connect():
    import pyodbc  # optional dependency; installed in the image, not required for tests

    return pyodbc.connect(settings.HGA_ODBC_DSN, timeout=30, readonly=True)


def fetch_wells(conn, since=None):
    sql = "SELECT WellID, WellName, Easting, Northing, Elevation, LastModified FROM dbo.Wells"
    params = []
    if since is not None:
        sql += " WHERE LastModified > ?"
        params.append(since)
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    for row in cur.fetchall():
        yield dict(zip(cols, row, strict=True))
