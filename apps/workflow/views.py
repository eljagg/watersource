"""Staff review queue and the per-item action panel (htmx partial)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import engine
from .models import WorkflowInstance, WorkflowStage


def staff_required(view):
    from functools import wraps

    @wraps(view)
    def _w(request, *a, **kw):
        if not request.user.is_staff_user and not request.user.is_superuser:
            return HttpResponseBadRequest("Staff only")
        return view(request, *a, **kw)

    return login_required(_w)


@staff_required
def queue(request):
    items = engine.queue_for(request.user).select_related("definition", "current_stage", "submitter").order_by("stage_entered_at")
    definition = request.GET.get("definition")
    if definition:
        items = items.filter(definition__code=definition)
    return render(request, "staff/queue.html", {"items": items[:200], "definition": definition})


@staff_required
def detail(request, pk):
    instance = get_object_or_404(WorkflowInstance.objects.select_related("definition", "current_stage"), pk=pk)
    return render(request, "staff/workflow_detail.html", {"instance": instance, "subject": instance.subject,
                  "return_targets": instance.current_stage.can_return_to.all() if instance.current_stage else []})


@staff_required
@require_POST
def act(request, pk):
    instance = get_object_or_404(WorkflowInstance, pk=pk)
    action = request.POST.get("action")
    comment = request.POST.get("comment", "")
    try:
        if action == "approve":
            classification = request.POST.get("classification")
            engine.approve(instance, request.user, comment, **({"classification": classification} if classification else {}))
        elif action == "reject":
            engine.reject(instance, request.user, comment)
        elif action == "return":
            target = get_object_or_404(WorkflowStage, pk=request.POST.get("stage"))
            engine.return_to(instance, request.user, target, comment)
        elif action == "request_info":
            engine.request_info(instance, request.user, comment)
        elif action == "comment":
            engine.comment(instance, request.user, comment)
        else:
            return HttpResponseBadRequest("Unknown action")
        messages.success(request, "Done.")
    except engine.WorkflowError as exc:
        messages.error(request, str(exc))
    if request.headers.get("HX-Request"):
        instance.refresh_from_db()
        return render(request, "staff/_workflow_panel.html", {"instance": instance, "subject": instance.subject,
                      "return_targets": instance.current_stage.can_return_to.all() if instance.current_stage else []})
    return redirect("workflow:detail", pk=pk)
