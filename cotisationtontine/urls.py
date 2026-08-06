from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .views import GroupDetailAPIView, MyGroupAPIView
from .views_api import (
    ActionLogViewSet,
    GroupMemberViewSet,
    GroupViewSet,
    VersementViewSet,
)


app_name = "cotisationtontine"


# ==========================================================
# API REST
# ==========================================================

router = DefaultRouter()

router.register(
    r"groups",
    GroupViewSet,
)

router.register(
    r"members",
    GroupMemberViewSet,
)

router.register(
    r"versements",
    VersementViewSet,
)

router.register(
    r"logs",
    ActionLogViewSet,
)


urlpatterns = [

    # ======================================================
    # API
    # ======================================================

    path(
        "api/",
        include(router.urls),
    ),

    path(
        "api/group/<int:group_id>/",
        GroupDetailAPIView.as_view(),
        name="api_group_detail",
    ),

    path(
        "api/my-group/",
        MyGroupAPIView.as_view(),
        name="api_my_group",
    ),


    # ======================================================
    # DASHBOARD
    # ======================================================

    path(
        "",
        views.dashboard_tontine_simple,
        name="home",
    ),

    path(
        "dashboard/",
        views.dashboard_tontine_simple,
        name="dashboard_tontine_simple",
    ),


    # ======================================================
    # GROUPES
    # ======================================================

    path(
        "groups/",
        views.group_list_view,
        name="group_list",
    ),

    path(
        "create/",
        views.ajouter_groupe_view,
        name="ajouter_groupe",
    ),

    path(
        "group/<int:group_id>/",
        views.group_detail,
        name="group_detail",
    ),


    # ======================================================
    # MEMBRES
    # ======================================================

    path(
        "group/<int:group_id>/membre/ajouter/",
        views.ajouter_membre_view,
        name="ajouter_membre",
    ),

    path(
        "group/<int:group_id>/membre/<int:membre_id>/editer/",
        views.editer_membre_view,
        name="editer_membre",
    ),

    path(
        "group/<int:group_id>/membre/<int:membre_id>/supprimer/",
        views.supprimer_membre_view,
        name="supprimer_membre",
    ),


    # ======================================================
    # VERSEMENTS MANUELS
    # ======================================================

    path(
        "versement/<int:member_id>/initier/",
        views.initier_versement,
        name="initier_versement",
    ),

    path(
        "versement/<int:versement_id>/valider/",
        views.valider_versement,
        name="valider_versement",
    ),

    path(
        "versement/<int:versement_id>/refuser/",
        views.refuser_versement,
        name="refuser_versement",
    ),


    # ======================================================
    # PAYDUNYA
    # ======================================================

    path(
        "paydunya/versement/<int:member_id>/initier/",
        views.paydunya_initier,
        name="paydunya_initier",
    ),

    path(
        "paydunya/callback/",
        views.paydunya_callback,
        name="paydunya_callback",
    ),

    path(
        "paydunya/return/",
        views.paydunya_return,
        name="paydunya_return",
    ),

    path(
        "paydunya/cancel/",
        views.paydunya_cancel,
        name="paydunya_cancel",
    ),


    # ======================================================
    # TIRAGE
    # ======================================================

    path(
        "group/<int:group_id>/tirage/",
        views.tirage_au_sort_view,
        name="tirage_au_sort",
    ),

    path(
        "group/<int:group_id>/tirage/resultat/",
        views.tirage_resultat_view,
        name="tirage_resultat",
    ),


    # ======================================================
    # CYCLE
    # ======================================================

    path(
        "group/<int:group_id>/reset-cycle/",
        views.reset_cycle_view,
        name="reset_cycle",
    ),


    # ======================================================
    # HISTORIQUE
    # ======================================================

    path(
        "group/<int:group_id>/historique-cycles/",
        views.historique_cycles_view,
        name="historique_cycles",
    ),

    path(
        "historique-actions/",
        views.historique_actions_view,
        name="historique_actions",
    ),
]