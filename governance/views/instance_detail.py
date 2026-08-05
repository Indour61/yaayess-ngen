from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from governance.models import (
    GovernanceDecisionLog,
    GovernanceInstance,
    GovernanceTask,
    GovernanceTransition,
)


CLOSED_TASK_STATUSES = (
    GovernanceTask.Status.COMPLETED,
    GovernanceTask.Status.CANCELLED,
)


@login_required
@permission_required(
    "governance.view_governanceinstance",
    raise_exception=True,
)
def governance_instance_detail(request, pk):
    """
    Affiche la fiche complète d’une instance de gouvernance.

    La page présente :
    - le projet et le workflow ;
    - l’étape actuelle et l’étape précédente ;
    - les indicateurs opérationnels ;
    - les tâches du dossier ;
    - les transitions disponibles ;
    - l’historique des décisions du moteur.
    """

    instance = get_object_or_404(
        GovernanceInstance.objects.select_related(
            "project",
            "project__group",
            "project__postal_office",
            "project__postal_office__region",
            "project__eligibility_policy",
            "workflow",
            "current_stage",
            "previous_stage",
            "started_by",
            "last_action_by",
        ),
        pk=pk,
    )

    # ======================================================
    # TÂCHES DU DOSSIER
    # ======================================================

    tasks = (
        GovernanceTask.objects
        .filter(instance=instance)
        .select_related(
            "stage",
            "assigned_to",
            "assigned_group",
            "assigned_by",
            "completed_by",
        )
        .order_by(
            "stage__order",
            "status",
            "due_at",
            "created_at",
        )
    )

    task_metrics = tasks.aggregate(
        total=Count("id"),
        completed=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.COMPLETED,
            ),
        ),
        cancelled=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.CANCELLED,
            ),
        ),
        pending=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.PENDING,
            ),
        ),
        assigned=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.ASSIGNED,
            ),
        ),
        in_progress=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.IN_PROGRESS,
            ),
        ),
        waiting=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.WAITING,
            ),
        ),
    )

    open_tasks_count = (
        tasks
        .exclude(status__in=CLOSED_TASK_STATUSES)
        .count()
    )

    # ======================================================
    # HISTORIQUE DES DÉCISIONS
    # ======================================================

    decision_logs = (
        GovernanceDecisionLog.objects
        .filter(instance=instance)
        .select_related(
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

    latest_decision = decision_logs.first()

    # ======================================================
    # ÉTAPES DU WORKFLOW
    # ======================================================

    workflow_stages = (
        instance.workflow.stages
        .filter(is_active=True)
        .select_related(
            "responsible_group",
        )
        .order_by("order")
    )

    # ======================================================
    # TRANSITIONS DISPONIBLES DEPUIS L’ÉTAPE ACTUELLE
    # ======================================================

    available_transitions = GovernanceTransition.objects.none()

    if instance.current_stage_id:
        available_transitions = (
            GovernanceTransition.objects
            .filter(
                workflow=instance.workflow,
                from_stage=instance.current_stage,
                is_active=True,
            )
            .select_related(
                "from_stage",
                "to_stage",
            )
            .order_by(
                "to_stage__order",
                "name",
            )
        )

    # ======================================================
    # CONTEXTE
    # ======================================================

    context = {
        "instance": instance,

        "tasks": tasks,
        "task_metrics": task_metrics,
        "open_tasks_count": open_tasks_count,

        "decision_logs": decision_logs[:20],
        "decision_logs_count": decision_logs.count(),
        "latest_decision": latest_decision,

        "workflow_stages": workflow_stages,
        "available_transitions": available_transitions,
    }

    return render(
        request,
        "governance/instances/detail.html",
        context,
    )