"""The four initial dashboards (design doc 13 §5) as declarative panel specifications.

Each dashboard lists its KPI tiles and panels; every panel names the ``bi`` view
it reads and the chart idiom the browser renders it with
(``static/js/dashboards.js``). Keeping the specification in Python means the
desk page, the wall page and the JSON endpoint all describe the same thing,
and WRA can see in one file what every number on the wall is built from.

Idioms (one y-axis per chart, direct labels, legend only for ≥2 series — §4.4):

* ``kpi``     — stat tile: value, unit, delta text
* ``hbar``    — ranked horizontal bars (sequential ramp when ``ranked``)
* ``vbar``    — vertical bars with direct labels
* ``line``    — one or more monthly/daily series, optional reference line
* ``stacked`` — stacked vertical bars by a category key
* ``status``  — count tiles coloured by the reserved status set
* ``list``    — short ranked list with a pill (longest-waiting items, alerts)

``wall_safe`` marks panels that contain no personal data and may appear on the
wall display (all of them today; the flag exists so a future staff-only panel is
excluded by design, not by accident).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Panel:
    """One dashboard panel bound to a bi view."""

    key: str
    title: str
    subtitle: str
    kind: str
    view: str
    span: int = 4  # of 12 columns on the wall / desk grid
    options: dict = field(default_factory=dict)
    wall_safe: bool = True


@dataclass(frozen=True)
class Kpi:
    """One stat tile. ``value`` / ``delta`` are column names of the kpi view; ``spark`` names a (view, column) series."""

    key: str
    title: str
    view: str
    value: str
    unit: str = ""
    delta: str = ""
    delta_label: str = ""
    good_when: str = "up"  # "up" | "down" | "flat" — which direction of change is good
    fmt: str = "int"  # int | pct | days | volume
    link: str = ""  # desk mode: click-through to the page that lists the underlying records (never used on the wall)


@dataclass(frozen=True)
class Dashboard:
    """A dashboard: slug, titles, question it answers, tiles and panels."""

    slug: str
    title: str
    question: str
    kpis: list[Kpi]
    panels: list[Panel]
    source_note: str


LICENSING = Dashboard(
    slug="licensing",
    title="Licensing overview",
    question="How is the licensing service performing this month and what needs a decision now?",
    source_note="Source: WaterSource bi.licensing views · applicant names never shown on this display",
    kpis=[
        Kpi("open", "Open applications", "bi.licensing_kpis", "applications_open", link="/licensing/applications/?status=under_review"),
        Kpi("turnaround", "Median turnaround", "bi.licensing_kpis", "median_days_to_decision_12m", unit="days", good_when="down", fmt="days"),
        Kpi("granted", "Granted, last 12 months", "bi.licensing_kpis", "granted_last_12m", delta="refused_last_12m", delta_label="refused"),
        Kpi("expiring", "Licences expiring in 90 days", "bi.licensing_kpis", "expiring_within_90_days", good_when="down", link="/licensing/licences/"),
    ],
    panels=[
        Panel("stages", "Applications by stage", "Where the open applications sit today", "hbar", "bi.application_stage_counts", span=5,
              options={"label": "stage", "value": "applications", "sort": "stage_order"}),
        Panel("monthly", "Received vs granted, last 12 months", "Monthly counts · dashed line is the 12-month average received", "line", "bi.applications_monthly", span=7,
              options={"x": "month", "series": [["received", "Received"], ["granted", "Granted"], ["refused", "Refused"]], "average_of": "received", "x_format": "month"}),
        Panel("parish", "Open applications by parish", "Top eight parishes", "hbar", "bi.open_applications_by_parish", span=4,
              options={"label": "parish", "value": "applications", "ranked": True, "limit": 8}),
        Panel("standard", "Turnaround vs 30-day service standard", "Median days from submission to decision", "line", "bi.applications_monthly", span=4,
              options={"x": "month", "series": [["median_days_to_decision", "Median days"]], "reference": {"value": 30, "label": "30-day standard"}, "area": True, "x_format": "month"}),
        Panel("waiting", "Needs attention", "Longest-waiting items at their current stage", "list", "bi.longest_waiting_applications", span=4,
              options={"ref": "reference", "who": ["source_name", "parish"], "pill": "days_waiting", "pill_unit": "days", "critical_at": 45, "serious_at": 30, "limit": 5}),
    ],
)

MONITORING = Dashboard(
    slug="monitoring",
    title="Water resources monitoring",
    question="What is the state of the island's water resources right now and where is it changing?",
    source_note="Source: WaterSource bi.monitoring views · approved data only; public-supply coordinates never shown",
    kpis=[
        Kpi("stations", "Stations reporting (7 days)", "bi.monitoring_kpis", "stations_reporting_7d", delta="stations_active", delta_label="active stations", good_when="up"),
        Kpi("below", "Wells below normal level", "bi.monitoring_kpis", "wells_below_normal", delta="wells_classed", delta_label="wells classed", good_when="down"),
        Kpi("share", "Abstraction vs granted", "bi.monitoring_kpis", "abstraction_share_pct", unit="%", delta="licences_over_limit", delta_label="licensees over limit", good_when="down", fmt="pct"),
        Kpi("awaiting", "Readings awaiting approval", "bi.monitoring_kpis", "rows_awaiting_approval", good_when="down", link="/admin/obs/wellwaterlevel/?approval_state__exact=pending"),
    ],
    panels=[
        Panel("gw_index", "Groundwater level index by basin, 24 months", "Monthly median depth to water, indexed to the basin's 10-year mean (100) · higher = deeper", "line", "bi.groundwater_index_by_basin", span=7,
              options={"x": "month", "group": "basin", "value": "index_value", "reference": {"value": 100, "label": "10-year mean"}, "x_format": "month", "markers": False, "min": 80, "max": 125}),
        Panel("well_status", "Well status, all monitored wells", "Latest reading (provisional included) classed against the well's approved record", "status", "bi.well_level_status", span=5,
              options={"key": "status", "order": ["much_below_normal", "below_normal", "normal", "above_normal", "much_above_normal", "no_recent_data", "insufficient_record"]}),
        Panel("share", "Abstraction vs granted by licence, latest month", "Reported volume as a share of the licensed limit · over 100 % is flagged", "hbar", "bi.abstraction_share_latest", span=5,
              options={"label": "licence_number", "value": "share_pct", "sort": "-share_pct", "limit": 8, "unit": "%", "critical_above": 100, "reference": 100, "label_width": 200}),
        Panel("wq", "Water-quality exceedances, last 90 days", "Approved samples outside the guideline value, by parameter", "vbar", "bi.wq_exceedances_90d", span=3,
              options={"label": "parameter", "value": "samples_exceeding", "sort": "-samples_exceeding"}),
        Panel("flow", "Station status", "Latest discharge (provisional readings included) classed against each station's approved record", "status", "bi.station_flow_status", span=4,
              options={"key": "status", "order": ["much_below_normal", "below_normal", "normal", "above_normal", "much_above_normal", "no_recent_data", "insufficient_record"], "compact": True}),
    ],
)

SUBMISSIONS = Dashboard(
    slug="submissions",
    title="Data submissions and quality",
    question="Is data flowing in, is it clean, and is the review queue under control?",
    source_note="Source: WaterSource bi.submissions views · submitter names never shown on this display",
    kpis=[
        Kpi("subs", "Submissions this month", "bi.submissions_kpis", "submissions_this_month", delta="rows_this_month", delta_label="rows"),
        Kpi("accept", "Acceptance rate, 90 days", "bi.submissions_kpis", "acceptance_rate_pct", unit="%", fmt="pct"),
        Kpi("flagged", "Rows flagged, 90 days", "bi.submissions_kpis", "rows_flagged_90d", good_when="down"),
        Kpi("review", "Items in review", "bi.submissions_kpis", "items_in_review", delta="median_review_days_90d", delta_label="median days to close", good_when="down", link="/workflow/queue/"),
    ],
    panels=[
        Panel("channels", "Submissions by month and channel", "Form, CSV upload and API, last 12 months", "stacked", "bi.submissions_monthly", span=7,
              options={"x": "month", "group": "channel", "value": "submissions", "x_format": "month"}),
        Panel("outcome", "Rows accepted, flagged and rejected by category", "Last 12 months", "stacked", "bi.submissions_monthly", span=5,
              options={"x": "category", "series": [["rows_accepted", "Accepted"], ["rows_flagged", "Flagged"], ["rows_rejected", "Rejected"]], "sum_by_x": True, "horizontal": True}),
        Panel("backlog", "Review backlog by age", "Open items at their current stage", "vbar", "bi.review_backlog_age", span=4,
              options={"label": "age_band", "value": "items", "sort": "band_order", "sum_by_label": True}),
        Panel("failures", "Top validation failures, 90 days", "Rows rejected, by field", "hbar", "bi.validation_failures", span=4,
              options={"label": "field", "value": "rows_failed", "ranked": True, "limit": 8}),
        Panel("grades", "Observation grades, 12 months", "Share of rows by grade, per series", "stacked", "bi.observation_grades", span=4,
              options={"x": "series", "group": "grade", "value": "rows", "horizontal": True, "percent": True}),
    ],
)

EXECUTIVE = Dashboard(
    slug="executive",
    title="Executive and compliance summary",
    question="Is WRA meeting its service and stewardship commitments?",
    source_note="Source: WaterSource bi.executive views · financial figures added once WRA confirms they may be displayed",
    kpis=[
        Kpi("active", "Active licences", "bi.executive_kpis", "active_licences"),
        Kpi("granted", "Granted this year", "bi.executive_kpis", "granted_this_year"),
        Kpi("standard", "Decided within 30 days", "bi.executive_kpis", "service_standard_pct_12m", unit="%", fmt="pct"),
        Kpi("volume", "Licensed daily volume", "bi.executive_kpis", "licensed_daily_volume_m3", unit="m³/day", fmt="volume"),
    ],
    panels=[
        Panel("status", "Licences by status", "All licences on record, by water source", "stacked", "bi.licences_by_status", span=4,
              options={"x": "status", "group": "water_source", "value": "licences"}),
        Panel("volume_parish", "Licensed volume by parish", "Active licences, m³/day", "hbar", "bi.licence_active_by_parish", span=4,
              options={"label": "parish", "value": "daily_volume_granted_m3", "ranked": True, "limit": 8, "sum_by_label": True, "fmt": "volume"}),
        Panel("standard_trend", "Service-standard compliance", "% of decisions within 30 days · target 80 %", "line", "bi.service_standard_monthly", span=4,
              options={"x": "month", "series": [["within_30_days_pct", "Within 30 days"]], "reference": {"value": 80, "label": "target"}, "area": True, "x_format": "month", "max": 100}),
        Panel("expiries", "Expiries and renewals, next 12 months", "Licences expiring each month and renewals already lodged", "stacked", "bi.expiries_next_12m", span=7,
              options={"x": "month", "series": [["expiring", "Expiring"], ["renewals_lodged", "Renewal lodged"]], "x_format": "month", "side_by_side": True}),
        Panel("governance", "Audit and data protection, 12 months", "Counts from the audit trail", "status", "bi.governance_kpis", span=5,
              options={"single_row": True, "items": [["failed_sign_ins_blocked", "Failed sign-ins blocked", "critical"], ["lockouts_active", "Accounts locked out", "serious"],
                                                      ["classification_changes_12m", "Classification changes", "s1"], ["corrections_approved_12m", "Corrections approved", "s3"],
                                                      ["subject_access_exports_12m", "Subject-access exports", "s1"], ["retention_sweeps_12m", "Retention sweeps run", "s3"]]}),
    ],
)

DASHBOARDS: dict[str, Dashboard] = {d.slug: d for d in (LICENSING, MONITORING, SUBMISSIONS, EXECUTIVE)}
#: Rotation order on the wall display.
WALL_ORDER = ["licensing", "monitoring", "submissions", "executive"]
