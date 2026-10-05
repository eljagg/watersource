"""Finance & Accounts export pages: licence register and abstraction returns as CSV (ToR H.xiii).

Restricted to the ``finance`` and ``administrator`` roles; every download is
written to the audit trail because the files carry licensee names. The same
data is available to Finance's own systems through the API
(``/api/v1/exports/finance/…``) with an API key belonging to a finance user.
"""
import csv
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts import roles
from apps.core import audit

from . import exports


def _finance_user(user) -> bool:
    return user.is_superuser or user.has_role(*roles.FINANCE_EXPORT_ROLES)


def _csv(filename: str, header: list[str], rows) -> HttpResponse:
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    w = csv.writer(resp)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return resp


def _period(request) -> tuple[date, date]:
    today = timezone.localdate()
    start = parse_date(request.GET.get("from", "")) or today.replace(day=1)
    end = parse_date(request.GET.get("to", "")) or today
    return start, end


@login_required
def finance_index(request):
    """Finance export page: pick a period, download the two CSV files."""
    if not _finance_user(request.user):
        raise Http404
    start, end = _period(request)
    return render(request, "integrations/finance.html", {"start": start, "end": end})


@login_required
def finance_licences_csv(request):
    """Licence register (active licences unless ``?status=``)."""
    if not _finance_user(request.user):
        raise Http404
    status = request.GET.get("status") or None
    audit.log("export.finance_licences", None, actor=request.user, summary=status or "active")
    return _csv(f"licences_{status or 'active'}_{timezone.localdate():%Y%m%d}.csv", exports.FINANCE_LICENCE_COLUMNS, exports.finance_licence_rows(status))


@login_required
def finance_abstraction_csv(request):
    """Abstraction returns against licences for the period ``?from=&to=``."""
    if not _finance_user(request.user):
        raise Http404
    start, end = _period(request)
    audit.log("export.finance_abstraction", None, actor=request.user, summary=f"{start} to {end}")
    from datetime import datetime, time

    tz = timezone.get_current_timezone()
    s = timezone.make_aware(datetime.combine(start, time.min), tz)
    e = timezone.make_aware(datetime.combine(end, time.max), tz)
    return _csv(f"abstraction_{start:%Y%m%d}_{end:%Y%m%d}.csv", exports.FINANCE_ABSTRACTION_COLUMNS, exports.finance_abstraction_rows(s, e))
