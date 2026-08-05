from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.shortcuts import get_object_or_404, render

from governance.models import (
    GovernanceDecisionLog,
    GovernanceTask,
)


@login_required
@permission_required(
    "governance.view_governancedecisionlog",
    raise_exception=True,
)
def governance_decision_log_detail(request, pk):
    """
    Affiche le rapport détaillé d’une décision produite
    par le moteur de gouvernance.

    La piste d’audit est strictement consultative.
    """

    log = get_object_or_404(
        GovernanceDecisionLog.objects.select_related(
            "instance",
            "instance__current_stage",
            "instance__previous_stage",
            "project",
            "project__group",
            "project__postal_office",
            "project__postal_office__region",
            "workflow",
            "from_stage",
            "to_stage",
            "transition",
            "actor",
        ),
        pk=pk,
    )

    # ======================================================
    # NORMALISATION DES DONNÉES JSON
    # ======================================================

    criteria = (
        log.criteria_snapshot
        if isinstance(log.criteria_snapshot, list)
        else []
    )

    blocking_reasons = (
        log.blocking_reasons
        if isinstance(log.blocking_reasons, list)
        else []
    )

    warnings = (
        log.warnings
        if isinstance(log.warnings, list)
        else []
    )

    engine_snapshot = (
        log.engine_snapshot
        if isinstance(log.engine_snapshot, dict)
        else {}
    )

    # ======================================================
    # JOURNAUX PRÉCÉDENT ET SUIVANT DU MÊME DOSSIER
    # ======================================================

    previous_log = (
        GovernanceDecisionLog.objects
        .filter(
            instance=log.instance,
            evaluated_at__lt=log.evaluated_at,
        )
        .order_by("-evaluated_at")
        .first()
    )

    next_log = (
        GovernanceDecisionLog.objects
        .filter(
            instance=log.instance,
            evaluated_at__gt=log.evaluated_at,
        )
        .order_by("evaluated_at")
        .first()
    )

    # ======================================================
    # TÂCHES LIÉES À L’ÉTAPE ÉVALUÉE
    # ======================================================

    related_tasks = GovernanceTask.objects.none()

    if log.from_stage_id:
        related_tasks = (
            GovernanceTask.objects
            .filter(
                instance=log.instance,
                stage=log.from_stage,
            )
            .select_related(
                "stage",
                "assigned_to",
                "assigned_group",
                "completed_by",
            )
            .order_by(
                "status",
                "due_at",
                "created_at",
            )
        )

    # ======================================================
    # CONTEXTE
    # ======================================================

    context = {
        "log": log,

        "criteria": criteria,
        "criteria_count": len(criteria),

        "blocking_reasons": blocking_reasons,
        "blocking_reasons_count": len(blocking_reasons),

        "warnings": warnings,
        "warnings_count": len(warnings),

        "engine_snapshot": engine_snapshot,

        "previous_log": previous_log,
        "next_log": next_log,

        "related_tasks": related_tasks,
    }

    return render(
        request,
        "governance/logs/detail.html",
        context,
    )