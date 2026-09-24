from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core import audit

from . import services
from .forms import ApplicationForm, DocumentForm
from .models import ApplicationDocument, ApplicationStatus, Licence, LicenceApplication


def _visible_applications(user):
    qs = LicenceApplication.objects.select_related("parish", "applicant")
    if user.is_staff_user or user.is_superuser:
        return qs
    return qs.filter(applicant_user=user)


@login_required
def application_list(request):
    qs = _visible_applications(request.user)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(reference__icontains=q) | Q(applicant_name__icontains=q) | Q(source_name__icontains=q))
    for param in ("status", "water_source", "parish"):
        if request.GET.get(param):
            qs = qs.filter(**{param: request.GET[param]})
    return render(request, "lic/application_list.html", {"applications": qs[:200], "q": q, "statuses": ApplicationStatus.choices})


@login_required
def application_create(request):
    form = ApplicationForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        app = form.save(commit=False)
        app.applicant_user = request.user
        app.applicant = services.party_for_user(request.user, app.applicant_name, app.applicant_address, app.applicant_email, app.applicant_phone)
        app.save()
        audit.log("licence.application_created", app)
        messages.success(request, f"Draft {app.reference} saved. Upload your documents, then submit.")
        return redirect(app)
    return render(request, "lic/application_form.html", {"form": form})


@login_required
def application_detail(request, reference):
    app = get_object_or_404(_visible_applications(request.user), reference=reference)
    doc_form = DocumentForm()
    return render(request, "lic/application_detail.html", {"app": app, "doc_form": doc_form, "workflow": app.workflow,
                  "can_edit": app.status == ApplicationStatus.DRAFT and app.applicant_user_id == request.user.pk})


@login_required
@require_POST
def application_upload(request, reference):
    app = get_object_or_404(_visible_applications(request.user), reference=reference)
    form = DocumentForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            services.attach_document(app, form, request.user)
            messages.success(request, "Document uploaded.")
        except ValueError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "; ".join(m for errs in form.errors.values() for m in errs))
    return redirect(app)


@login_required
@require_POST
def application_submit(request, reference):
    app = get_object_or_404(LicenceApplication, reference=reference, applicant_user=request.user)
    try:
        services.submit_application(app, request.user)
        messages.success(request, f"Application {app.reference} submitted. You will be notified at each stage.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect(app)


@login_required
def document_download(request, pk):
    doc = get_object_or_404(ApplicationDocument.objects.select_related("application"), pk=pk)
    if not (request.user.is_staff_user or request.user.is_superuser or doc.application.applicant_user_id == request.user.pk):
        raise Http404
    audit.log("licence.document_downloaded", doc, summary=doc.original_name)
    return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.original_name)


@login_required
def licence_list(request):
    qs = Licence.objects.select_related("licensee", "parish")
    if not (request.user.is_staff_user or request.user.is_superuser):
        qs = qs.filter(licensee__accounts=request.user)
    return render(request, "lic/licence_list.html", {"licences": qs[:200]})


@login_required
def licence_detail(request, number):
    lic = get_object_or_404(Licence.objects.select_related("licensee", "parish", "application"), number=number)
    if not (request.user.is_staff_user or request.user.is_superuser or lic.licensee.accounts.filter(pk=request.user.pk).exists()):
        raise Http404
    return render(request, "lic/licence_detail.html", {"licence": lic})
