from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.shortcuts import render

from governance.services.dashboard_service import (
    get_governance_dashboard_context,
)


@login_required
@permission_required(
    "governance.view_governanceinstance",
    raise_exception=True,
)
def governance_dashboard(request):
    """
    Tableau de bord institutionnel de la gouvernance.

    Affiche les principaux indicateurs de gouvernance :
    - KPI globaux ;
    - répartition des dossiers par étape ;
    - dossiers nécessitant une action ;
    - tâches en retard ;
    - dernières décisions du moteur.
    """

    context = get_governance_dashboard_context(
        workflow_id=request.GET.get("workflow") or None,
        region_id=request.GET.get("region") or None,
        postal_office_id=request.GET.get("postal_office") or None,
        status=request.GET.get("status") or None,
    )

    return render(
        request=request,
        template_name="governance/dashboard.html",
        context=context,
    )