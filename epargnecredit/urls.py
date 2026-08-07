from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .api_views import (
    CreateVersementAPI,
    DashboardEpargneAPI,
    GroupMembersAPI,
    UserGroupsAPI,
    UserStatsAPI,
    UserVersementsAPI,
)
from .views import remboursements, versements
from .views_api import (
    ActionLogViewSet,
    GroupMemberViewSet,
    GroupViewSet,
    VersementViewSet,
)


app_name = "epargnecredit"


# ==========================================================
# API REST
# ==========================================================

router = DefaultRouter()

router.register(
    r"groups",
    GroupViewSet,
    basename="group",
)

router.register(
    r"members",
    GroupMemberViewSet,
    basename="group-member",
)

router.register(
    r"versements",
    VersementViewSet,
    basename="versement",
)

router.register(
    r"logs",
    ActionLogViewSet,
    basename="action-log",
)


urlpatterns = [

    # ======================================================
    # API REST
    # ======================================================

    path(
        "api/",
        include(router.urls),
    ),

    # ======================================================
    # DASHBOARD
    # ======================================================

    path(
        "dashboard/",
        views.dashboard_epargne_credit,
        name="dashboard_epargne_credit",
    ),

    # ======================================================
    # GROUPES
    # ======================================================

    path(
        "",
        views.group_list_view,
        name="group_list",
    ),

    path(
        "create/",
        views.ajouter_groupe_view,
        name="ajouter_groupe",
    ),

    path(
        "groupe/<int:group_id>/",
        views.group_detail,
        name="group_detail",
    ),

    # ======================================================
    # MEMBRES
    # ======================================================

    path(
        "groupe/<int:group_id>/membre/ajouter/",
        views.ajouter_membre_view,
        name="ajouter_membre",
    ),

    # ======================================================
    # VERSEMENTS
    # ======================================================

    path(
        "versement/initier/<int:member_id>/",
        versements.initier_versement,
        name="initier_versement",
    ),

    path(
        "versement/valider/<int:versement_id>/",
        versements.valider_versement,
        name="valider_versement",
    ),

    path(
        "versement/refuser/<int:versement_id>/",
        versements.refuser_versement,
        name="refuser_versement",
    ),

    # ======================================================
    # PAYDUNYA — VERSEMENTS
    # ======================================================

    path(
        "paydunya/versement/return/",
        versements.paydunya_versement_return,
        name="paydunya_versement_return",
    ),

    path(
        "paydunya/versement/cancel/",
        versements.paydunya_versement_cancel,
        name="paydunya_versement_cancel",
    ),

    path(
        "paydunya/versement/ipn/",
        versements.paydunya_versement_ipn,
        name="paydunya_versement_ipn",
    ),

    # ======================================================
    # PRÊTS
    # ======================================================

    path(
        "pret/nouveau/<int:member_id>/",
        views.demande_pret,
        name="demande_pret",
    ),

    path(
        "pret/<int:pk>/valider/",
        views.pret_valider,
        name="pret_valider",
    ),

    path(
        "pret/<int:pk>/refuser/",
        views.pret_refuser,
        name="pret_refuser",
    ),

    path(
        "pret/<int:pk>/remboursement/",
        remboursements.pret_remboursement_detail,
        name="pret_remboursement_detail",
    ),

    # ======================================================
    # REMBOURSEMENTS
    # ======================================================

    path(
        "remboursement/<int:group_id>/",
        remboursements.group_detail_remboursement,
        name="group_detail_remboursement",
    ),

    path(
        "remboursement/payer/<int:member_id>/",
        remboursements.initier_paiement_remboursement,
        name="initier_paiement_remboursement",
    ),

    # ======================================================
    # PAYDUNYA — REMBOURSEMENTS
    # ======================================================

    path(
        "paydunya/remboursement/return/",
        remboursements.paydunya_remboursement_return,
        name="paydunya_remboursement_return",
    ),

    path(
        "paydunya/remboursement/cancel/",
        remboursements.paydunya_remboursement_cancel,
        name="paydunya_remboursement_cancel",
    ),

    path(
        "paydunya/remboursement/ipn/",
        remboursements.paydunya_remboursement_ipn,
        name="paydunya_remboursement_ipn",
    ),

    # ======================================================
    # CYCLE
    # ======================================================

    path(
        "groupe/<int:group_id>/reset-cycle/",
        views.reset_cycle_view,
        name="reset_cycle",
    ),

    path(
        "epargne/<int:group_id>/partager-fin-de-cycle/",
        views.share_cycle_view,
        name="share_cycle",
    ),

    # ======================================================
    # HISTORIQUE
    # ======================================================

    path(
        "groupe/<int:group_id>/historique-cycles/",
        views.historique_cycles_view,
        name="historique_cycles",
    ),

    path(
        "historique-actions/",
        views.historique_actions_view,
        name="historique_actions",
    ),

    # ======================================================
    # API MOBILE
    # ======================================================

    path(
        "api/epargne/dashboard/",
        DashboardEpargneAPI.as_view(),
        name="api_dashboard_epargne",
    ),

    path(
        "api/epargne/groupes/",
        UserGroupsAPI.as_view(),
        name="api_user_groups",
    ),

    path(
        "api/epargne/group/<int:group_id>/membres/",
        GroupMembersAPI.as_view(),
        name="api_group_members",
    ),

    path(
        "api/epargne/versements/",
        UserVersementsAPI.as_view(),
        name="api_user_versements",
    ),

    path(
        "api/epargne/versement/create/",
        CreateVersementAPI.as_view(),
        name="api_create_versement",
    ),

    path(
        "api/epargne/stats/",
        UserStatsAPI.as_view(),
        name="api_user_stats",
    ),
]
