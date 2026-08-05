from django.urls import path
from django.views.generic import RedirectView

from .views import (
    governance_dashboard,
    governance_decision_log_detail,
    governance_decision_log_list,
    governance_instance_detail,
    governance_instance_list,
    governance_task_list,
)


app_name = "governance"


urlpatterns = [
    # ==========================================================
    # DASHBOARD
    # ==========================================================

    path(
        "dashboard/",
        governance_dashboard,
        name="dashboard",
    ),

    # ==========================================================
    # DOSSIERS DE GOUVERNANCE
    # ==========================================================

    path(
        "instances/",
        governance_instance_list,
        name="instance_list",
    ),

    # Redirection si aucun UUID n’est fourni.
    path(
        "instances/detail/",
        RedirectView.as_view(
            pattern_name="governance:instance_list",
            permanent=False,
        ),
        name="instance_detail_redirect",
    ),

    path(
        "instances/detail/<uuid:pk>/",
        governance_instance_detail,
        name="instance_detail_alias",
    ),

    path(
        "instances/<uuid:pk>/",
        governance_instance_detail,
        name="instance_detail",
    ),

    # ==========================================================
    # TÂCHES
    # ==========================================================

    path(
        "tasks/",
        governance_task_list,
        name="task_list",
    ),

    # ==========================================================
    # JOURNAL DES DÉCISIONS
    # ==========================================================

    path(
        "logs/",
        governance_decision_log_list,
        name="decision_log_list",
    ),

    # Redirection si aucun UUID n’est fourni.
    path(
        "logs/detail/",
        RedirectView.as_view(
            pattern_name="governance:decision_log_list",
            permanent=False,
        ),
        name="decision_log_detail_redirect",
    ),

    path(
        "logs/detail/<uuid:pk>/",
        governance_decision_log_detail,
        name="decision_log_detail_alias",
    ),

    path(
        "logs/<uuid:pk>/",
        governance_decision_log_detail,
        name="decision_log_detail",
    ),
]
