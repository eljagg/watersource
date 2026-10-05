"""Staff review queue and the per-item action panel (htmx partial)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import engine
from .models import WorkflowInstance, WorkflowStage


def staff_required(view):
    """Decorator: require a WRA staff user (403 otherwise)."""
    from functools import wraps

    @wraps(view)
    def _w(request, *a, **kw):
        if not request.user.is_staff_user and not request.user.is_superuser:
            return HttpResponseBadRequest("Staff only")
        return view(request, *a, **kw)

    return login_required(_w)


@staff_required
def queue(request):
    """Items awaiting the user's stage groups."""
    items = engine.queue_for(request.user).select_related("definition", "current_stage", "submitter").order_by("stage_entered_at")
    definition = request.GET.get("definition")
    if definition:
        items = items.filter(definition__code=definition)
    my_stages = [] if request.user.is_superuser else sorted({s.name for s in WorkflowStage.objects.filter(approver_group__in=request.user.groups.all())})
    return render(request, "staff/queue.html", {"items": items[:200], "definition": definition, "my_stages": my_stages})


@staff_required
def detail(request, pk):
    """Workflow detail with history and the action panel."""
    instance = get_object_or_404(WorkflowInstance.objects.select_related("definition", "current_stage"), pk=pk)
    return render(request, "staff/workflow_detail.html", {"instance": instance, "subject": instance.subject,
                  "return_targets": instance.current_stage.can_return_to.all() if instance.current_stage else []})


@staff_required
@require_POST
def act(request, pk):
    """Handle an action from the panel (approve/reject/return/info/comment).

    Always answers with a full-page redirect so the outcome message, the updated
    history and the new status are visible. Actions that move the item away from
    the user's stage go back to the review queue; comments stay on the item.
    """
    instance = get_object_or_404(WorkflowInstance, pk=pk)
    action = request.POST.get("action")
    comment = request.POST.get("comment", "")
    name = instance.summary
    try:
        if action == "approve":
            classification = request.POST.get("classification")
            engine.approve(instance, request.user, comment, **({"classification": classification} if classification else {}))
            instance.refresh_from_db()
            if instance.is_open:
                messages.success(request, f"Approved — {name} has moved on to the {instance.current_stage.name} stage.")
            else:
                messages.success(request, f"Approved and closed — {name}.")
        elif action == "reject":
            engine.reject(instance, request.user, comment)
            messages.success(request, f"Rejected — {name}. The submitter has been notified with your reason.")
        elif action == "return":
            target = get_object_or_404(WorkflowStage, pk=request.POST.get("stage"))
            engine.return_to(instance, request.user, target, comment)
            messages.success(request, f"Returned — {name} is back at the {target.name} stage.")
        elif action == "request_info":
            engine.request_info(instance, request.user, comment)
            messages.success(request, f"Information requested — {name} is now waiting on the submitter. It returns to your queue when they resubmit.")
        elif action == "comment":
            engine.comment(instance, request.user, comment)
            messages.success(request, "Comment added.")
            return _go("workflow:detail", request, pk=pk)
        else:
            return HttpResponseBadRequest("Unknown action")
    except engine.WorkflowError as exc:
        messages.error(request, str(exc))
        return _go("workflow:detail", request, pk=pk)
    return _go("workflow:queue", request)


def _go(name, request, **kw):
    """Redirect; for an htmx request use HX-Redirect so the whole page (messages, history) reloads."""
    url = reverse(name, kwargs=kw or None)
    if request.headers.get("HX-Request"):
        resp = HttpResponse(status=204)
        resp["HX-Redirect"] = url
        return resp
    return redirect(url)
