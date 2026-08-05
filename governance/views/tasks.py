from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.shortcuts import render

from governance.models import GovernanceTask


@login_required
@permission_required(
    "governance.view_governancetask",
    raise_exception=True,
)
def governance_task_list(request):
    """
    Liste des tâches.
    """

    tasks = (
        GovernanceTask.objects
        .select_related(
            "instance",
            "stage",
        )
        .order_by("status", "due_at")
    )

    return render(
        request,
        "governance/tasks/list.html",
        {
            "tasks": tasks,
        },
    )