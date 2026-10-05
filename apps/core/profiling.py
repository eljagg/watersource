"""Source-data profiling for the migration workstream (Milestone 3 — Data Quality Assessment Report).

``profile_files()`` reads WRA's legacy extracts (CSV or Excel, any number of
files) and produces the facts the M3 report is built from, per column: inferred
type, completeness, distinct values, min/max, date range and gaps, whitespace and
encoding issues, candidate keys and duplicate rows, and — for columns that look
like site, parish or licence references — the match rate against WaterSource's
reference tables (exact, alias, and case/space-insensitive). Nothing is written
to the database. The command ``manage.py profile_source`` renders the result as
Markdown (the report body) and JSON (for the migration toolkit, Sprint 4).

Only the standard library and openpyxl are used so the command runs on the
WRA app-vm without extra packages.
"""
from __future__ import annotations

import csv
import io
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

DATE_PATTERNS = [
    ("%Y-%m-%d", "ISO"), ("%d/%m/%Y", "d/m/Y"), ("%m/%d/%Y", "m/d/Y"), ("%d-%b-%Y", "d-Mon-Y"), ("%d-%b-%y", "d-Mon-y"),
    ("%Y-%m-%d %H:%M:%S", "ISO datetime"), ("%d/%m/%Y %H:%M", "d/m/Y H:M"), ("%Y/%m/%d", "Y/m/d"), ("%d %b %Y", "d Mon Y"),
]
NULL_TOKENS = {"", "na", "n/a", "null", "none", "-", "--", "?", "nil", "#n/a", "missing", "unknown"}
MAX_SAMPLE = 200000


@dataclass
class ColumnProfile:
    """Facts about one column."""

    name: str
    rows: int = 0
    blank: int = 0
    null_tokens: Counter = field(default_factory=Counter)
    types: Counter = field(default_factory=Counter)
    inferred: str = "text"
    distinct: int = 0
    examples: list = field(default_factory=list)
    numeric_min: float | None = None
    numeric_max: float | None = None
    numeric_mean: float | None = None
    numeric_outliers: int = 0
    date_min: str | None = None
    date_max: str | None = None
    date_formats: Counter = field(default_factory=Counter)
    leading_trailing_space: int = 0
    mixed_case_variants: int = 0
    non_ascii: int = 0
    max_length: int = 0
    reference_match: dict | None = None
    top_values: list = field(default_factory=list)

    @property
    def completeness(self) -> float:
        """Share of rows with a non-blank value."""
        return 0.0 if not self.rows else round(100.0 * (self.rows - self.blank) / self.rows, 1)


@dataclass
class FileProfile:
    """Facts about one file."""

    path: str
    rows: int
    columns: list[ColumnProfile]
    duplicate_rows: int
    candidate_keys: list[str]
    encoding: str
    sheet: str = ""
    issues: list[str] = field(default_factory=list)


def _read_rows(path: Path) -> tuple[list[str], list[list[str]], str, str]:
    """Return (header, rows, encoding, sheet) for CSV/TSV/XLSX."""
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else f"column_{i + 1}" for i, h in enumerate(next(it, []))]
        rows = [["" if v is None else (v.isoformat() if isinstance(v, (date, datetime)) else str(v)) for v in r] for r in it]
        return header, rows, "xlsx", ws.title
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text, enc = raw.decode("latin-1", errors="replace"), "latin-1 (replaced)"
    dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|") if text.strip() else csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = [h.strip() for h in next(reader, [])]
    rows = [r for r in reader if any(c.strip() for c in r)]
    return header, rows, enc, ""


def _classify(v: str) -> tuple[str, object]:
    s = v.strip()
    if s.lower() in NULL_TOKENS:
        return "blank", None
    if re.fullmatch(r"[-+]?\d+", s):
        return "integer", int(s)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?", s.replace(",", "")):
        try:
            return "decimal", float(s.replace(",", ""))
        except ValueError:
            pass
    for fmt, label in DATE_PATTERNS:
        try:
            return "date:" + label, datetime.strptime(s, fmt)
        except ValueError:
            continue
    if s.lower() in ("yes", "no", "true", "false", "y", "n"):
        return "boolean", s.lower() in ("yes", "true", "y")
    return "text", s


def profile_columns(header: list[str], rows: list[list[str]], reference: dict[str, dict] | None = None) -> list[ColumnProfile]:
    """Profile every column of a table. ``reference`` maps a column-name regex to a lookup dict (normalised name → canonical)."""
    cols = [ColumnProfile(name=h or f"column_{i + 1}") for i, h in enumerate(header)]
    for r in rows[:MAX_SAMPLE]:
        for i, c in enumerate(cols):
            v = r[i] if i < len(r) else ""
            c.rows += 1
            kind, parsed = _classify(v)
            if kind == "blank":
                c.blank += 1
                if v.strip():
                    c.null_tokens[v.strip()] += 1
                continue
            c.types[kind.split(":")[0]] += 1
            if kind.startswith("date:"):
                c.date_formats[kind[5:]] += 1
            if v != v.strip():
                c.leading_trailing_space += 1
            if any(ord(ch) > 127 for ch in v):
                c.non_ascii += 1
            c.max_length = max(c.max_length, len(v))
    # second pass for distinct / numeric / date stats (bounded sample)
    for i, c in enumerate(cols):
        values = [r[i] if i < len(r) else "" for r in rows[:MAX_SAMPLE]]
        nonblank = [v for v in values if _classify(v)[0] != "blank"]
        counter = Counter(v.strip() for v in nonblank)
        c.distinct = len(counter)
        c.top_values = counter.most_common(5)
        c.examples = [v for v, _ in counter.most_common(3)]
        lowered = Counter(v.strip().lower().replace("  ", " ") for v in nonblank)
        c.mixed_case_variants = c.distinct - len(lowered)
        dominant = c.types.most_common(1)[0][0] if c.types else "text"
        total = sum(c.types.values()) or 1
        c.inferred = dominant if c.types[dominant] / total >= 0.9 else "mixed"
        if dominant in ("integer", "decimal"):
            nums = [float(_classify(v)[1]) for v in nonblank if _classify(v)[0] in ("integer", "decimal")]
            if nums:
                c.numeric_min, c.numeric_max, c.numeric_mean = min(nums), max(nums), round(statistics.fmean(nums), 4)
                if len(nums) >= 8:
                    med = statistics.median(nums)
                    mad = statistics.median([abs(n - med) for n in nums]) or 0
                    if mad:
                        c.numeric_outliers = sum(1 for n in nums if abs(0.6745 * (n - med) / mad) > 3.5)
        if dominant == "date":
            ds = [_classify(v)[1] for v in nonblank if _classify(v)[0].startswith("date:")]
            if ds:
                c.date_min, c.date_max = min(ds).date().isoformat(), max(ds).date().isoformat()
        if reference:
            for pattern, lookup in reference.items():
                if re.search(pattern, c.name, re.I):
                    c.reference_match = match_rate(counter, lookup)
                    break
    return cols


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def match_rate(counter: Counter, lookup: dict[str, str]) -> dict:
    """How many distinct values resolve to a reference row: exact, normalised, unmatched (with the top unmatched values)."""
    exact = norm = 0
    unmatched: Counter = Counter()
    for value, n in counter.items():
        if value in lookup.values():
            exact += 1
        elif _norm(value) in lookup:
            norm += 1
        else:
            unmatched[value] += n
    total = len(counter) or 1
    return {"distinct": len(counter), "exact": exact, "normalised": norm, "unmatched": len(unmatched),
            "match_pct": round(100.0 * (exact + norm) / total, 1), "top_unmatched": unmatched.most_common(10)}


def candidate_keys(header: list[str], rows: list[list[str]]) -> list[str]:
    """Columns (or pairs) whose values are unique and complete — likely primary keys."""
    n = len(rows)
    keys = []
    for i, h in enumerate(header):
        vals = [r[i].strip() if i < len(r) else "" for r in rows]
        if n and all(vals) and len(set(vals)) == n:
            keys.append(h)
    if not keys:
        for i, a in enumerate(header):
            for j in range(i + 1, min(len(header), i + 6)):
                vals = [(r[i] if i < len(r) else "", r[j] if j < len(r) else "") for r in rows]
                if n and all(all(v) for v in vals) and len(set(vals)) == n:
                    keys.append(f"{a} + {header[j]}")
    return keys[:5]


def profile_file(path: Path, reference: dict | None = None) -> FileProfile:
    """Profile one CSV/XLSX file."""
    header, rows, enc, sheet = _read_rows(path)
    cols = profile_columns(header, rows, reference)
    dup = len(rows) - len({tuple(c.strip() for c in r) for r in rows})
    issues = []
    if enc not in ("utf-8", "utf-8-sig", "xlsx"):
        issues.append(f"File is not UTF-8 ({enc}); accented names will need re-encoding on load.")
    if dup:
        issues.append(f"{dup} fully duplicated row(s).")
    widths = Counter(len(r) for r in rows)
    if len(widths) > 1:
        issues.append(f"Rows have inconsistent column counts ({dict(widths)}); check for unquoted delimiters.")
    seen = Counter(h.lower() for h in header)
    for h, n in seen.items():
        if n > 1:
            issues.append(f"Header '{h}' appears {n} times.")
    for c in cols:
        if c.inferred == "mixed":
            issues.append(f"Column '{c.name}' mixes types ({dict(c.types)}).")
        if len(c.date_formats) > 1:
            issues.append(f"Column '{c.name}' uses {len(c.date_formats)} date formats ({dict(c.date_formats)}).")
        if c.null_tokens:
            issues.append(f"Column '{c.name}' uses placeholder blanks {dict(c.null_tokens.most_common(3))}.")
        if c.reference_match and c.reference_match["match_pct"] < 95:
            issues.append(f"Column '{c.name}': only {c.reference_match['match_pct']}% of values match the reference list.")
    return FileProfile(path=str(path), rows=len(rows), columns=cols, duplicate_rows=dup, candidate_keys=candidate_keys(header, rows), encoding=enc, sheet=sheet, issues=issues)


def reference_lookups() -> dict[str, dict]:
    """Normalised-name → canonical lookups for wells, stations, parishes, basins and licences (empty when the DB is unavailable)."""
    out: dict[str, dict] = {}
    try:
        from apps.lic.models import Licence
        from apps.ref.models import Basin, Parish, StreamflowStation, Well

        def names(qs, attr="name", aliases=False):
            d = {}
            for obj in qs:
                d[_norm(getattr(obj, attr))] = getattr(obj, attr)
                if aliases:
                    for a in getattr(obj, "aliases", None) or []:
                        d[_norm(a)] = getattr(obj, attr)
            return d

        out[r"well|borehole|bore"] = names(Well.objects.all(), aliases=True)
        out[r"station|gauge|gauging"] = names(StreamflowStation.objects.all(), aliases=True)
        out[r"parish"] = names(Parish.objects.all())
        out[r"basin"] = names(Basin.objects.all())
        out[r"licen[cs]e"] = names(Licence.objects.all(), attr="number")
    except Exception:  # noqa: BLE001 — profiling must work without a database too
        return {}
    return out


def render_markdown(profiles: list[FileProfile], title: str = "Data Quality Assessment Report (Milestone 3)") -> str:
    """The report body: summary, per-file findings, per-column table."""
    out = [f"# {title}", "", f"Generated {datetime.now():%d %B %Y %H:%M} by `manage.py profile_source`.", ""]
    out += ["## Summary", "", "| File | Rows | Columns | Duplicate rows | Candidate key | Encoding | Issues |", "|---|---:|---:|---:|---|---|---:|"]
    for p in profiles:
        out.append(f"| {Path(p.path).name}{(' / ' + p.sheet) if p.sheet else ''} | {p.rows:,} | {len(p.columns)} | {p.duplicate_rows:,} | {', '.join(p.candidate_keys) or '—'} | {p.encoding} | {len(p.issues)} |")
    for p in profiles:
        out += ["", f"## {Path(p.path).name}", ""]
        if p.issues:
            out += ["**Findings**", ""] + [f"- {i}" for i in p.issues] + [""]
        out += ["| Column | Type | Complete | Distinct | Min | Max | Dates | Spaces | Case variants | Reference match | Examples |", "|---|---|---:|---:|---|---|---|---:|---:|---|---|"]
        for c in p.columns:
            mn = c.numeric_min if c.numeric_min is not None else ""
            mx = c.numeric_max if c.numeric_max is not None else ""
            dates = f"{c.date_min} → {c.date_max}" if c.date_min else ""
            ref = f"{c.reference_match['match_pct']}% ({c.reference_match['unmatched']} unmatched)" if c.reference_match else ""
            ex = ", ".join(str(e)[:24] for e in c.examples)
            out.append(f"| {c.name} | {c.inferred} | {c.completeness}% | {c.distinct:,} | {mn} | {mx} | {dates} | {c.leading_trailing_space} | {c.mixed_case_variants} | {ref} | {ex} |")
        unmatched = [(c.name, c.reference_match["top_unmatched"]) for c in p.columns if c.reference_match and c.reference_match["top_unmatched"]]
        for name, items in unmatched:
            out += ["", f"Unmatched values in **{name}** (value × rows): " + "; ".join(f"{v} ×{n}" for v, n in items)]
        outl = [(c.name, c.numeric_outliers) for c in p.columns if c.numeric_outliers]
        if outl:
            out += ["", "Numeric outliers (robust z > 3.5): " + ", ".join(f"{n} ({k})" for n, k in outl)]
    out += ["", "## How to read this report", "",
            "Completeness is the share of rows with a value. Candidate key is a column (or pair) that is unique and complete, the natural join key for migration. "
            "Reference match is the share of distinct values that resolve to a WaterSource reference row exactly or after trimming spaces, case and punctuation; "
            "the unmatched list is the work queue for the data-cleaning workshop. Outliers are flagged with a robust z-score so one bad value does not hide others.", ""]
    return "\n".join(out)


def to_json(profiles: list[FileProfile]) -> dict:
    """JSON-serialisable form for the migration toolkit."""
    def col(c: ColumnProfile):
        d = c.__dict__.copy()
        d["types"], d["null_tokens"], d["date_formats"] = dict(c.types), dict(c.null_tokens), dict(c.date_formats)
        d["completeness"] = c.completeness
        return d

    return {"generated_at": datetime.now().isoformat(), "files": [{**{k: v for k, v in p.__dict__.items() if k != "columns"}, "columns": [col(c) for c in p.columns]} for p in profiles]}
