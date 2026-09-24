from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.catalog.models import DataCategory
from apps.catalog.services import csv_template, form_class_for
from apps.core.uploads import validate_upload

from . import services
from .models import Submission


def _visible(user):
    qs = Submission.objects.select_related("category_version__category", "submitter")
    if user.is_staff_user or user.is_superuser:
        return qs
    return qs.filter(submitter=user)


@login_required
def index(request):
    categories = DataCategory.objects.filter(is_active=True)
    return render(request, "submissions/index.html", {"categories": categories, "submissions": _visible(request.user)[:50]})


@login_required
def new_form(request, code):
    category = get_object_or_404(DataCategory, code=code, is_active=True)
    version = category.current_version
    if version is None:
        raise Http404("No published version")
    Form = form_class_for(version)
    form = Form(request.POST or None)
    if request.method == "POST" and form.is_valid():
        sub = services.create_submission(version, [form.validated_row], request.user, note=request.POST.get("note", ""))
        messages.success(request, f"Submission #{sub.pk} received" + (f" with {len(form.flags)} note(s) for the reviewer." if form.flags else "."))
        return redirect(sub)
    return render(request, "submissions/form.html", {"category": category, "version": version, "form": form})


@login_required
def new_csv(request, code):
    category = get_object_or_404(DataCategory, code=code, is_active=True, allow_csv=True)
    version = category.current_version
    if request.method == "POST" and request.FILES.get("file"):
        f = request.FILES["file"]
        try:
            validate_upload(f, {"text/csv": [".csv"], "text/plain": [".csv"], "application/csv": [".csv"]})
            sub = services.create_from_csv(version, f, request.user, note=request.POST.get("note", ""))
            messages.success(request, f"File received: {sub.accepted_count} accepted, {sub.flagged_count} flagged, {sub.rejected_count} rejected.")
            return redirect(sub)
        except Exception as exc:  # validation errors surface to the user
            messages.error(request, str(exc))
    return render(request, "submissions/csv.html", {"category": category, "version": version})


@login_required
def template(request, code):
    category = get_object_or_404(DataCategory, code=code)
    version = category.current_version
    resp = HttpResponse(csv_template(version), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{category.code}_v{version.version}_template.csv"'
    return resp


@login_required
def detail(request, pk):
    sub = get_object_or_404(_visible(request.user), pk=pk)
    return render(request, "submissions/detail.html", {"sub": sub, "records": sub.records.all()[:500], "workflow": sub.workflow})
