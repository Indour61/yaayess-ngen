from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from governance.models import GovernanceDecisionLog


@login_required
@permission_required(
    "governance.view_governancedecisionlog",
    raise_exception=True,
)
def governance_decision_log_list(request):
    """
    Journal complet des décisions du moteur de gouvernance.
    """

    logs = (
        GovernanceDecisionLog.objects
        .select_related(
            "instance",
            "project",
            "workflow",
            "from_stage",
            "to_stage",
            "transition",
            "actor",
        )
        .order_by(
            "-evaluated_at",
            "-created_at",
        )
    )

    search = request.GET.get("q", "").strip()
    decision_code = request.GET.get("decision", "").strip()
    application_status = request.GET.get(
        "application_status",
        "",
    ).strip()
    workflow_id = request.GET.get("workflow", "").strip()
    from_stage_id = request.GET.get("from_stage", "").strip()
    eligible = request.GET.get("eligible", "").strip()

    if search:
        logs = logs.filter(
            Q(reference__icontains=search)
            | Q(instance__reference__icontains=search)
            | Q(project__reference__icontains=search)
            | Q(project__title__icontains=search)
            | Q(workflow__code__icontains=search)
            | Q(workflow__name__icontains=search)
            | Q(summary__icontains=search)
            | Q(actor__nom__icontains=search)
            | Q(actor__phone__icontains=search)
        )

    if decision_code:
        logs = logs.filter(
            decision_code=decision_code,
        )

    if application_status:
        logs = logs.filter(
            application_status=application_status,
        )

    if workflow_id:
        logs = logs.filter(
            workflow_id=workflow_id,
        )

    if from_stage_id:
        logs = logs.filter(
            from_stage_id=from_stage_id,
        )

    if eligible == "yes":
        logs = logs.filter(eligible=True)

    elif eligible == "no":
        logs = logs.filter(eligible=False)

    paginator = Paginator(
        logs,
        20,
    )

    page_obj = paginator.get_page(
        request.GET.get("page"),
    )

    filter_source = (
        GovernanceDecisionLog.objects
        .select_related(
            "workflow",
            "from_stage",
        )
    )

    workflows = (
        filter_source
        .values(
            "workflow_id",
            "workflow__code",
            "workflow__name",
        )
        .distinct()
        .order_by(
            "workflow__name",
        )
    )

    stages = (
        filter_source
        .exclude(from_stage__isnull=True)
        .values(
            "from_stage_id",
            "from_stage__code",
            "from_stage__name",
            "from_stage__order",
        )
        .distinct()
        .order_by(
            "from_stage__order",
        )
    )

    context = {
        "page_obj": page_obj,
        "logs": page_obj.object_list,

        "search": search,
        "selected_decision": decision_code,
        "selected_application_status": application_status,
        "selected_workflow_id": workflow_id,
        "selected_from_stage_id": from_stage_id,
        "selected_eligible": eligible,

        "decision_choices": (
            GovernanceDecisionLog.DecisionCode.choices
        ),
        "application_status_choices": (
            GovernanceDecisionLog.ApplicationStatus.choices
        ),

        "workflows": workflows,
        "stages": stages,
        "total_results": paginator.count,
    }

    return render(
        request,
        "governance/logs/list.html",
        context,
    )


@login_required
@permission_required(
    "governance.view_governancedecisionlog",
    raise_exception=True,
)
def governance_decision_log_detail(
    request,
    pk,
):
    """
    Détail complet d'une décision de gouvernance.
    """

    log = get_object_or_404(
        GovernanceDecisionLog.objects.select_related(
            "instance",
            "project",
            "workflow",
            "from_stage",
            "to_stage",
            "transition",
            "actor",
        ),
        pk=pk,
    )

    context = {
        "log": log,
    }

    return render(
        request,
        "governance/logs/detail.html",
        context,
    )
