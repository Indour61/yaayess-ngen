from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import WeeklyExecutiveDashboard
from .services import get_live_dashboard_metrics


logger = logging.getLogger(__name__)

EXECUTIVE_DASHBOARD_PERMISSION = (
    "pilotage.access_executive_dashboard"
)


def get_latest_published_dashboard() -> WeeklyExecutiveDashboard:
    """
    Retourne le tableau de bord publié le plus récent.

    Le classement est explicite afin de ne pas dépendre uniquement
    de l'ordre défini dans la classe Meta du modèle.
    """
    dashboard = (
        WeeklyExecutiveDashboard.objects
        .filter(is_published=True)
        .select_related("created_by")
        .order_by(
            "-period_end",
            "-week_number",
            "-updated_at",
        )
        .first()
    )

    if dashboard is None:
        raise Http404(
            "Aucun tableau de bord exécutif publié "
            "n’est disponible."
        )

    return dashboard


def build_fallback_metrics(
    dashboard: WeeklyExecutiveDashboard,
) -> dict[str, Any]:
    """
    Construit des valeurs de secours à partir des données enregistrées
    dans le tableau de bord.

    Cette fonction permet à la page HTML de rester accessible même
    lorsqu'une requête de calcul temps réel rencontre une erreur.
    """
    return {
        "period_start": dashboard.period_start.isoformat(),
        "period_end": dashboard.period_end.isoformat(),

        "accounts_created": dashboard.accounts_created,
        "active_users": dashboard.active_users,
        "groups_created": dashboard.groups_created,
        "registered_members": dashboard.registered_members,

        "contributions_count": dashboard.contributions_count,
        "contributions_amount": float(
            dashboard.contributions_amount
        ),

        "savings_deposits_count": (
            dashboard.savings_deposits_count
        ),
        "savings_amount": float(
            dashboard.savings_amount
        ),

        "credits_granted_count": (
            dashboard.credits_granted_count
        ),
        "credits_amount": float(
            dashboard.credits_amount
        ),

        "repayments_count": dashboard.repayments_count,
        "repayments_amount": 0.0,

        "investments_count": dashboard.investments_count,
        "investments_amount": float(
            dashboard.investments_amount
        ),

        "successful_transaction_rate": float(
            dashboard.successful_transaction_rate
        ),
        "platform_availability": float(
            dashboard.platform_availability
        ),
        "average_response_time": float(
            dashboard.average_response_time
        ),
        "critical_incidents": dashboard.critical_incidents,

        "total_transactions": 0,
        "successful_transactions": 0,

        "updated_at": timezone.localtime(
            dashboard.updated_at
        ).strftime("%d/%m/%Y à %H:%M:%S"),

        "is_fallback": True,
    }


def add_no_cache_headers(
    response: HttpResponse,
) -> HttpResponse:
    """
    Empêche le navigateur et les intermédiaires de mettre en cache
    les données sensibles du tableau de bord.
    """
    response["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    return response


@login_required
@permission_required(
    EXECUTIVE_DASHBOARD_PERMISSION,
    raise_exception=True,
)
@require_GET
@never_cache
def executive_dashboard(
    request: HttpRequest,
) -> HttpResponse:
    """
    Affiche le dernier tableau de bord exécutif publié.

    En cas d'erreur du calcul en temps réel, la page reste accessible
    avec les dernières valeurs enregistrées dans la base.
    """
    dashboard = get_latest_published_dashboard()

    metrics_error = None

    try:
        live_metrics = get_live_dashboard_metrics(
            dashboard
        )
        live_metrics["is_fallback"] = False

    except Exception as exc:
        logger.exception(
            "Erreur pendant le calcul des KPI du tableau "
            "de bord exécutif %s.",
            dashboard.pk,
        )

        live_metrics = build_fallback_metrics(
            dashboard
        )

        metrics_error = (
            "Les indicateurs en temps réel sont temporairement "
            "indisponibles. Les dernières valeurs enregistrées "
            "sont affichées."
        )

    context = {
        "dashboard": dashboard,
        "live_metrics": live_metrics,
        "metrics_error": metrics_error,
        "refresh_interval_seconds": 15,
    }

    response = render(
        request,
        "pilotage/executive_dashboard.html",
        context,
    )

    return add_no_cache_headers(response)


@login_required
@permission_required(
    EXECUTIVE_DASHBOARD_PERMISSION,
    raise_exception=True,
)
@require_GET
@never_cache
def executive_dashboard_data(
    request: HttpRequest,
) -> JsonResponse:
    """
    Retourne les KPI actualisés au format JSON.

    Cette route est appelée périodiquement par le JavaScript
    du tableau de bord.
    """
    dashboard = get_latest_published_dashboard()

    try:
        live_metrics = get_live_dashboard_metrics(
            dashboard
        )

    except Exception as exc:
        logger.exception(
            "Erreur pendant l'actualisation JSON des KPI "
            "du tableau de bord exécutif %s.",
            dashboard.pk,
        )

        response = JsonResponse(
            {
                "success": False,
                "error": (
                    "Les indicateurs en temps réel sont "
                    "temporairement indisponibles."
                ),
                "error_code": "LIVE_METRICS_UNAVAILABLE",
                "dashboard_id": dashboard.pk,
                "server_time": timezone.localtime().isoformat(),
            },
            status=503,
        )

        return add_no_cache_headers(response)

    response = JsonResponse(
        {
            "success": True,
            "dashboard": {
                "id": dashboard.pk,
                "week_number": dashboard.week_number,
                "period_start": (
                    dashboard.period_start.isoformat()
                ),
                "period_end": (
                    dashboard.period_end.isoformat()
                ),
                "overall_status": dashboard.overall_status,
                "progress_percentage": float(
                    dashboard.progress_percentage
                ),
                "updated_at": timezone.localtime(
                    dashboard.updated_at
                ).isoformat(),
            },
            "metrics": live_metrics,
            "server_time": timezone.localtime().isoformat(),
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )

    return add_no_cache_headers(response)