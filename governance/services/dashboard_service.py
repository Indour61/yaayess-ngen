from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from governance.models import (
    GovernanceDecisionLog,
    GovernanceInstance,
    GovernanceStage,
    GovernanceTask,
)


# ==========================================================
# CONSTANTES
# ==========================================================

CLOSED_INSTANCE_STATUSES = (
    GovernanceInstance.Status.COMPLETED,
    GovernanceInstance.Status.CANCELLED,
    GovernanceInstance.Status.REJECTED,
)

CLOSED_TASK_STATUSES = (
    GovernanceTask.Status.COMPLETED,
    GovernanceTask.Status.CANCELLED,
)

ATTENTION_INSTANCE_STATUSES = (
    GovernanceInstance.Status.WAITING,
    GovernanceInstance.Status.SUSPENDED,
    GovernanceInstance.Status.REJECTED,
)

PRIORITY_TASK_LEVELS = (
    GovernanceTask.Priority.URGENT,
    GovernanceTask.Priority.CRITICAL,
)


# ==========================================================
# OUTILS
# ==========================================================

def _percentage(
    numerator: int | Decimal,
    denominator: int | Decimal,
) -> Decimal:
    """
    Calcule un pourcentage sécurisé entre 0 et 100.
    """

    if not denominator:
        return Decimal("0.00")

    value = (
        Decimal(str(numerator))
        / Decimal(str(denominator))
        * Decimal("100.00")
    )

    return value.quantize(
        Decimal("0.01")
    )


def _normalize_filter_value(value) -> str | None:
    """
    Nettoie une valeur issue d'un filtre GET.

    Les valeurs vides, 'all' et 'none' sont considérées
    comme une absence de filtre.
    """

    if value is None:
        return None

    normalized = str(value).strip()

    if not normalized:
        return None

    if normalized.lower() in {
        "all",
        "none",
        "null",
    }:
        return None

    return normalized


# ==========================================================
# QUERYSETS DE BASE
# ==========================================================

def get_governance_instances_queryset() -> QuerySet:
    """
    Retourne le queryset optimisé des instances de gouvernance.
    """

    return (
        GovernanceInstance.objects
        .select_related(
            "project",
            "project__group",
            "project__postal_office",
            "project__postal_office__region",
            "workflow",
            "current_stage",
            "previous_stage",
            "started_by",
            "last_action_by",
        )
    )


def get_governance_tasks_queryset() -> QuerySet:
    """
    Retourne le queryset optimisé des tâches de gouvernance.
    """

    return (
        GovernanceTask.objects
        .select_related(
            "instance",
            "instance__project",
            "instance__project__postal_office",
            "instance__project__postal_office__region",
            "stage",
            "assigned_to",
            "assigned_group",
            "assigned_by",
            "completed_by",
        )
    )


def get_governance_decisions_queryset() -> QuerySet:
    """
    Retourne le queryset optimisé des décisions de gouvernance.
    """

    return (
        GovernanceDecisionLog.objects
        .select_related(
            "instance",
            "project",
            "project__group",
            "project__postal_office",
            "project__postal_office__region",
            "workflow",
            "from_stage",
            "to_stage",
            "transition",
            "actor",
        )
    )


# ==========================================================
# FILTRES
# ==========================================================

def apply_dashboard_filters(
    *,
    instances: QuerySet,
    tasks: QuerySet,
    decisions: QuerySet,
    workflow_id: str | None = None,
    region_id: str | None = None,
    postal_office_id: str | None = None,
    status: str | None = None,
) -> tuple[QuerySet, QuerySet, QuerySet]:
    """
    Applique les mêmes filtres territoriaux et fonctionnels aux
    instances, tâches et décisions.
    """

    workflow_id = _normalize_filter_value(
        workflow_id
    )
    region_id = _normalize_filter_value(
        region_id
    )
    postal_office_id = _normalize_filter_value(
        postal_office_id
    )
    status = _normalize_filter_value(
        status
    )

    if workflow_id:
        instances = instances.filter(
            workflow_id=workflow_id
        )
        tasks = tasks.filter(
            instance__workflow_id=workflow_id
        )
        decisions = decisions.filter(
            workflow_id=workflow_id
        )

    if region_id:
        instances = instances.filter(
            project__postal_office__region_id=region_id
        )
        tasks = tasks.filter(
            instance__project__postal_office__region_id=region_id
        )
        decisions = decisions.filter(
            project__postal_office__region_id=region_id
        )

    if postal_office_id:
        instances = instances.filter(
            project__postal_office_id=postal_office_id
        )
        tasks = tasks.filter(
            instance__project__postal_office_id=postal_office_id
        )
        decisions = decisions.filter(
            project__postal_office_id=postal_office_id
        )

    if status:
        instances = instances.filter(
            status=status
        )
        tasks = tasks.filter(
            instance__status=status
        )
        decisions = decisions.filter(
            instance__status=status
        )

    return (
        instances,
        tasks,
        decisions,
    )


# ==========================================================
# KPI DES INSTANCES
# ==========================================================

def get_instance_metrics(
    *,
    instances: QuerySet,
    now=None,
) -> dict[str, Any]:
    """
    Calcule les KPI des dossiers de gouvernance.
    """

    now = now or timezone.now()

    aggregates = instances.aggregate(
        total=Count("id"),
        active=Count(
            "id",
            filter=Q(
                status=GovernanceInstance.Status.ACTIVE
            ),
        ),
        waiting=Count(
            "id",
            filter=Q(
                status=GovernanceInstance.Status.WAITING
            ),
        ),
        suspended=Count(
            "id",
            filter=Q(
                status=GovernanceInstance.Status.SUSPENDED
            ),
        ),
        rejected=Count(
            "id",
            filter=Q(
                status=GovernanceInstance.Status.REJECTED
            ),
        ),
        completed=Count(
            "id",
            filter=Q(
                status=GovernanceInstance.Status.COMPLETED
            ),
        ),
        cancelled=Count(
            "id",
            filter=Q(
                status=GovernanceInstance.Status.CANCELLED
            ),
        ),
        average_score=Avg(
            "governance_score"
        ),
    )

    overdue = (
        instances
        .filter(
            due_at__isnull=False,
            due_at__lt=now,
        )
        .exclude(
            status__in=CLOSED_INSTANCE_STATUSES,
        )
        .count()
    )

    total = aggregates["total"] or 0
    completed = aggregates["completed"] or 0

    return {
        "total_instances": total,
        "active_instances": aggregates["active"] or 0,
        "waiting_instances": aggregates["waiting"] or 0,
        "suspended_instances": aggregates["suspended"] or 0,
        "rejected_instances": aggregates["rejected"] or 0,
        "completed_instances": completed,
        "cancelled_instances": aggregates["cancelled"] or 0,
        "overdue_instances": overdue,
        "average_score": (
            aggregates["average_score"]
            or Decimal("0.00")
        ),
        "completion_rate": _percentage(
            completed,
            total,
        ),
    }


# ==========================================================
# KPI DES TÂCHES
# ==========================================================

def get_task_metrics(
    *,
    tasks: QuerySet,
    now=None,
) -> dict[str, Any]:
    """
    Calcule les KPI des tâches de gouvernance.
    """

    now = now or timezone.now()

    aggregates = tasks.aggregate(
        total=Count("id"),
        completed=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.COMPLETED
            ),
        ),
        cancelled=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.CANCELLED
            ),
        ),
        pending=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.PENDING
            ),
        ),
        assigned=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.ASSIGNED
            ),
        ),
        in_progress=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.IN_PROGRESS
            ),
        ),
        waiting=Count(
            "id",
            filter=Q(
                status=GovernanceTask.Status.WAITING
            ),
        ),
    )

    open_tasks_queryset = tasks.exclude(
        status__in=CLOSED_TASK_STATUSES,
    )

    open_tasks = open_tasks_queryset.count()

    overdue_tasks = (
        open_tasks_queryset
        .filter(
            due_at__isnull=False,
            due_at__lt=now,
        )
        .count()
    )

    urgent_tasks = (
        open_tasks_queryset
        .filter(
            priority__in=PRIORITY_TASK_LEVELS,
        )
        .count()
    )

    unassigned_tasks = (
        open_tasks_queryset
        .filter(
            assigned_to__isnull=True,
            assigned_group__isnull=True,
        )
        .count()
    )

    total = aggregates["total"] or 0
    completed = aggregates["completed"] or 0

    return {
        "total_tasks": total,
        "open_tasks": open_tasks,
        "completed_tasks": completed,
        "cancelled_tasks": aggregates["cancelled"] or 0,
        "pending_tasks": aggregates["pending"] or 0,
        "assigned_tasks": aggregates["assigned"] or 0,
        "in_progress_tasks": aggregates["in_progress"] or 0,
        "waiting_tasks": aggregates["waiting"] or 0,
        "overdue_tasks": overdue_tasks,
        "urgent_tasks": urgent_tasks,
        "unassigned_tasks": unassigned_tasks,
        "task_completion_rate": _percentage(
            completed,
            total,
        ),
    }


# ==========================================================
# KPI DES DÉCISIONS
# ==========================================================

def get_decision_metrics(
    *,
    decisions: QuerySet,
) -> dict[str, Any]:
    """
    Calcule les KPI liés aux décisions du moteur.
    """

    aggregates = decisions.aggregate(
        total=Count("id"),
        applied=Count(
            "id",
            filter=Q(
                application_status=(
                    GovernanceDecisionLog
                    .ApplicationStatus
                    .APPLIED
                )
            ),
        ),
        not_applied=Count(
            "id",
            filter=Q(
                application_status=(
                    GovernanceDecisionLog
                    .ApplicationStatus
                    .NOT_APPLIED
                )
            ),
        ),
        recommended=Count(
            "id",
            filter=Q(
                application_status=(
                    GovernanceDecisionLog
                    .ApplicationStatus
                    .RECOMMENDED
                )
            ),
        ),
        overridden=Count(
            "id",
            filter=Q(
                application_status=(
                    GovernanceDecisionLog
                    .ApplicationStatus
                    .OVERRIDDEN
                )
            ),
        ),
        failed=Count(
            "id",
            filter=Q(
                application_status=(
                    GovernanceDecisionLog
                    .ApplicationStatus
                    .FAILED
                )
            ),
        ),
        information_requests=Count(
            "id",
            filter=Q(
                decision_code=(
                    GovernanceDecisionLog
                    .DecisionCode
                    .REQUEST_INFO
                )
            ),
        ),
        blocked=Count(
            "id",
            filter=Q(
                decision_code=(
                    GovernanceDecisionLog
                    .DecisionCode
                    .BLOCK
                )
            ),
        ),
        rejected=Count(
            "id",
            filter=Q(
                decision_code=(
                    GovernanceDecisionLog
                    .DecisionCode
                    .REJECT
                )
            ),
        ),
        manual_reviews=Count(
            "id",
            filter=Q(
                decision_code=(
                    GovernanceDecisionLog
                    .DecisionCode
                    .MANUAL_REVIEW
                )
            ),
        ),
        advances=Count(
            "id",
            filter=Q(
                decision_code=(
                    GovernanceDecisionLog
                    .DecisionCode
                    .ADVANCE
                )
            ),
        ),
        average_decision_score=Avg(
            "global_score"
        ),
    )

    total = aggregates["total"] or 0
    applied = aggregates["applied"] or 0

    return {
        "total_decisions": total,
        "applied_decisions": applied,
        "not_applied_decisions": (
            aggregates["not_applied"] or 0
        ),
        "recommended_decisions": (
            aggregates["recommended"] or 0
        ),
        "overridden_decisions": (
            aggregates["overridden"] or 0
        ),
        "failed_decisions": (
            aggregates["failed"] or 0
        ),
        "information_requests": (
            aggregates["information_requests"] or 0
        ),
        "blocked_decisions": (
            (aggregates["blocked"] or 0)
            + (aggregates["rejected"] or 0)
        ),
        "rejected_decisions": (
            aggregates["rejected"] or 0
        ),
        "manual_reviews": (
            aggregates["manual_reviews"] or 0
        ),
        "advance_decisions": (
            aggregates["advances"] or 0
        ),
        "average_decision_score": (
            aggregates["average_decision_score"]
            or Decimal("0.00")
        ),
        "applied_decision_rate": _percentage(
            applied,
            total,
        ),
    }


# ==========================================================
# PIPELINE DES ÉTAPES
# ==========================================================

def get_stage_pipeline(
    *,
    workflow_id: str | None = None,
    region_id: str | None = None,
    postal_office_id: str | None = None,
) -> QuerySet:
    """
    Retourne les étapes avec le nombre d'instances actuellement
    présentes sur chacune d'elles.
    """

    workflow_id = _normalize_filter_value(
        workflow_id
    )
    region_id = _normalize_filter_value(
        region_id
    )
    postal_office_id = _normalize_filter_value(
        postal_office_id
    )

    instance_filter = Q()

    if region_id:
        instance_filter &= Q(
            current_instances__project__postal_office__region_id=region_id
        )

    if postal_office_id:
        instance_filter &= Q(
            current_instances__project__postal_office_id=postal_office_id
        )

    stages = (
        GovernanceStage.objects
        .filter(
            is_active=True,
        )
        .select_related(
            "workflow",
            "responsible_group",
        )
    )

    if workflow_id:
        stages = stages.filter(
            workflow_id=workflow_id
        )

    return (
        stages
        .annotate(
            instance_total=Count(
                "current_instances",
                filter=instance_filter,
                distinct=True,
            ),
            active_total=Count(
                "current_instances",
                filter=(
                    instance_filter
                    & Q(
                        current_instances__status=(
                            GovernanceInstance.Status.ACTIVE
                        )
                    )
                ),
                distinct=True,
            ),
            waiting_total=Count(
                "current_instances",
                filter=(
                    instance_filter
                    & Q(
                        current_instances__status=(
                            GovernanceInstance.Status.WAITING
                        )
                    )
                ),
                distinct=True,
            ),
            overdue_total=Count(
                "current_instances",
                filter=(
                    instance_filter
                    & Q(
                        current_instances__due_at__lt=timezone.now()
                    )
                    & ~Q(
                        current_instances__status__in=(
                            CLOSED_INSTANCE_STATUSES
                        )
                    )
                ),
                distinct=True,
            ),
        )
        .order_by(
            "workflow__code",
            "order",
        )
    )


# ==========================================================
# LISTES OPÉRATIONNELLES
# ==========================================================

def get_attention_instances(
    *,
    instances: QuerySet,
    now=None,
    limit: int = 10,
) -> QuerySet:
    """
    Retourne les dossiers en attente, suspendus, rejetés
    ou en retard.
    """

    now = now or timezone.now()

    return (
        instances
        .filter(
            Q(
                status__in=ATTENTION_INSTANCE_STATUSES
            )
            | Q(
                due_at__isnull=False,
                due_at__lt=now,
            )
        )
        .order_by(
            "due_at",
            "-updated_at",
        )[:limit]
    )


def get_priority_tasks(
    *,
    tasks: QuerySet,
    now=None,
    limit: int = 10,
) -> QuerySet:
    """
    Retourne les tâches urgentes, critiques ou en retard.
    """

    now = now or timezone.now()

    return (
        tasks
        .exclude(
            status__in=CLOSED_TASK_STATUSES,
        )
        .filter(
            Q(
                due_at__isnull=False,
                due_at__lt=now,
            )
            | Q(
                priority__in=PRIORITY_TASK_LEVELS
            )
        )
        .order_by(
            "due_at",
            "-priority",
            "created_at",
        )[:limit]
    )


def get_recent_decisions(
    *,
    decisions: QuerySet,
    limit: int = 10,
) -> QuerySet:
    """
    Retourne les dernières décisions du moteur.
    """

    return decisions.order_by(
        "-evaluated_at",
    )[:limit]


def get_recent_instances(
    *,
    instances: QuerySet,
    limit: int = 8,
) -> QuerySet:
    """
    Retourne les dernières instances créées.
    """

    return instances.order_by(
        "-created_at",
    )[:limit]


# ==========================================================
# SERVICE PRINCIPAL
# ==========================================================

def get_governance_dashboard_context(
    *,
    workflow_id: str | None = None,
    region_id: str | None = None,
    postal_office_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """
    Construit toutes les données nécessaires au Dashboard
    Gouvernance.

    Cette fonction constitue le point d'entrée principal du
    service et peut être utilisée par une vue HTML ou une API.
    """

    now = timezone.now()

    instances = get_governance_instances_queryset()
    tasks = get_governance_tasks_queryset()
    decisions = get_governance_decisions_queryset()

    (
        filtered_instances,
        filtered_tasks,
        filtered_decisions,
    ) = apply_dashboard_filters(
        instances=instances,
        tasks=tasks,
        decisions=decisions,
        workflow_id=workflow_id,
        region_id=region_id,
        postal_office_id=postal_office_id,
        status=status,
    )

    instance_metrics = get_instance_metrics(
        instances=filtered_instances,
        now=now,
    )

    task_metrics = get_task_metrics(
        tasks=filtered_tasks,
        now=now,
    )

    decision_metrics = get_decision_metrics(
        decisions=filtered_decisions,
    )

    context = {
        "dashboard_generated_at": now,

        # Filtres actifs
        "selected_workflow_id": (
            _normalize_filter_value(workflow_id)
        ),
        "selected_region_id": (
            _normalize_filter_value(region_id)
        ),
        "selected_postal_office_id": (
            _normalize_filter_value(
                postal_office_id
            )
        ),
        "selected_status": (
            _normalize_filter_value(status)
        ),

        # Pipeline
        "stage_pipeline": get_stage_pipeline(
            workflow_id=workflow_id,
            region_id=region_id,
            postal_office_id=postal_office_id,
        ),

        # Données opérationnelles
        "attention_instances": get_attention_instances(
            instances=filtered_instances,
            now=now,
        ),
        "priority_tasks": get_priority_tasks(
            tasks=filtered_tasks,
            now=now,
        ),
        "recent_decisions": get_recent_decisions(
            decisions=filtered_decisions,
        ),
        "recent_instances": get_recent_instances(
            instances=filtered_instances,
        ),
    }

    context.update(
        instance_metrics
    )
    context.update(
        task_metrics
    )
    context.update(
        decision_metrics
    )

    return context