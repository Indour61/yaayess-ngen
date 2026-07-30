"""
epargnecredit/views/dashboard.py
--------------------------------
Vues du tableau de bord Épargne & Crédit.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from accounts.models import Notification
from epargnecredit.models import (
    ActionLog,
    Group,
    Versement,
)


# ==========================================================
# Landing
# ==========================================================

def landing_view(request):
    """
    Page d'accueil publique.
    Si l'utilisateur est connecté, il est redirigé vers
    le tableau de bord.
    """

    if request.user.is_authenticated:
        return redirect("epargnecredit:dashboard_epargne_credit")

    return render(request, "landing.html")


# ==========================================================
# Dashboard principal
# ==========================================================

@login_required
def dashboard_epargne_credit(request):
    """
    Tableau de bord principal de l'application
    Épargne & Crédit.
    """

    user = request.user

    # ======================================================
    # Vérification validation utilisateur
    # ======================================================

    if (
        not user.is_superuser
        and not getattr(user, "is_validated", False)
    ):

        try:
            attente_url = reverse(
                "accounts:attente_validation"
            )

        except NoReverseMatch:

            attente_url = reverse(
                "accounts:login"
            )

        messages.error(
            request,
            (
                "⛔ Votre compte doit être validé "
                "par l'administrateur avant "
                "d'accéder à l'application "
                "Épargne & Crédit."
            ),
        )

        return redirect(attente_url)

    # ======================================================
    # Groupes administrés
    # ======================================================

    groupes_admin = (
        Group.objects
        .filter(admin=user)
        .prefetch_related("membres_ec")
        .order_by("-date_creation")
    )

    # ======================================================
    # Groupes où l'utilisateur est membre
    # ======================================================

    groupes_membre = (
        Group.objects
        .filter(membres_ec=user)
        .exclude(admin=user)
        .distinct()
    )

    # ======================================================
    # Actions récentes
    # ======================================================

    dernieres_actions = (
        ActionLog.objects
        .filter(user=user)
        .select_related("group")
        .order_by("-date")[:10]
    )

    # ======================================================
    # Notifications
    # ======================================================

    notifications = (
        Notification.objects
        .order_by("-created_at")[:5]
    )

    # ======================================================
    # Total des versements
    # ======================================================

    total_versements = (
        Versement.objects
        .filter(
            member__user=user,
            statut="VALIDE",
        )
        .aggregate(total=Sum("montant"))
        .get("total")
        or 0
    )

    # ======================================================
    # Nombre total de groupes
    # ======================================================

    total_groupes = (
        Group.objects
        .filter(
            Q(admin=user)
            | Q(membres_ec=user)
        )
        .distinct()
        .count()
    )

    # ======================================================
    # Versements récents
    # ======================================================

    date_limite = (
        timezone.now()
        - timedelta(days=30)
    )

    versements_recents = (
        Versement.objects
        .filter(
            member__user=user,
            date_creation__gte=date_limite,
        )
        .select_related(
            "member__group"
        )
        .order_by("-date_creation")[:5]
    )

    # ======================================================
    # Statistiques des groupes administrés
    # ======================================================

    stats_groupes_admin = (
        Versement.objects
        .filter(
            member__group__admin=user,
            statut="VALIDE",
        )
        .values(
            "member__group__id",
            "member__group__nom",
        )
        .annotate(
            versements_total=Sum("montant")
        )
        .order_by("-versements_total")
    )

    # ======================================================
    # Contexte
    # ======================================================

    context = {

        "groupes_admin": groupes_admin,
        "groupes_membre": groupes_membre,

        "dernieres_actions": dernieres_actions,
        "notifications": notifications,

        "total_versements": total_versements,
        "total_groupes": total_groupes,

        "versements_recents": versements_recents,
        "stats_groupes_admin": stats_groupes_admin,

    }

    return render(
        request,
        "epargnecredit/dashboard.html",
        context,
    )


# ==========================================================
# Dashboard simple (fallback)
# ==========================================================

@login_required
def dashboard_view(request):
    """
    Vue simplifiée du dashboard.
    """

    return render(
        request,
        "epargnecredit/dashboard.html",
    )