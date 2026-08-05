from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.shortcuts import render

from governance.models import GovernanceInstance


@login_required
@permission_required(
    "governance.view_governanceinstance",
    raise_exception=True,
)
def governance_instance_list(request):
    """
    Liste des dossiers de gouvernance.
    """

    instances = (
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
        .order_by(
            "-updated_at",
            "-created_at",
        )
    )

    return render(
        request,
        "governance/instances/list.html",
        {
            "instances": instances,
        },
    )