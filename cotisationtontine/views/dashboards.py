from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from cotisationtontine.models import ActionLog, Group, Versement

@login_required
def dashboard_tontine_simple(request):
    """
    Dashboard principal Tontine
    Visible uniquement si l'utilisateur administre un groupe
    """

    user = request.user

    # =====================================================
    # ðŸ”’ SÃ©curitÃ© : vÃ©rifier si utilisateur admin d'un groupe
    # =====================================================

    groupes_admin = (
        Group.objects
        .filter(admin=user)
        .prefetch_related("membres")
        .order_by("-date_creation")
    )

    if not groupes_admin.exists():
        messages.warning(
            request,
            "Vous nâ€™Ãªtes administrateur dâ€™aucun groupe."
        )
#        return redirect("accounts:login")
        return render(
            request,
            "cotisationtontine/no_group.html"
        )
    # =====================================================
    # ðŸ‘¥ Groupes oÃ¹ l'utilisateur est membre
    # =====================================================

    groupes_membre = (
        Group.objects
        .filter(membres__user=user)
        .exclude(admin=user)
        .distinct()
    )

    # =====================================================
    # ðŸ“ DerniÃ¨res actions utilisateur
    # =====================================================

    dernieres_actions = (
        ActionLog.objects
        .filter(user=user)
        .select_related("group")
        .order_by("-date")[:10]
    )

    # =====================================================
    # ðŸ’° Total versements utilisateur
    # =====================================================

    total_versements = (
        Versement.objects
        .filter(member__user=user, statut="VALIDE")
        .aggregate(total=Sum("montant"))
        .get("total") or 0
    )

    # =====================================================
    # ðŸ“Š Nombre total groupes utilisateur
    # =====================================================

    total_groupes = (
        Group.objects
        .filter(membres__user=user)
        .distinct()
        .count()
    )

    # =====================================================
    # ðŸ“… Versements rÃ©cents (30 jours)
    # =====================================================

    date_limite = timezone.now() - timedelta(days=30)

    versements_recents = (
        Versement.objects
        .filter(
            member__user=user,
            date_creation__gte=date_limite
        )
        .select_related("member__group")
        .order_by("-date_creation")[:5]
    )

    # =====================================================
    # ðŸ“ˆ Stats groupes administrÃ©s
    # =====================================================

    stats_groupes_admin = (
        Versement.objects
        .filter(member__group__admin=user, statut="VALIDE")
        .values(
            "member__group__id",
            "member__group__nom"
        )
        .annotate(
            versements_total=Sum("montant")
        )
        .order_by("-versements_total")
    )

    # =====================================================
    # ðŸ“¦ Context
    # =====================================================

    context = {
        "groupes_admin": groupes_admin,
        "groupes_membre": groupes_membre,
        "action_logs": dernieres_actions,  # ðŸ”¥ CORRECTION ICI
        "total_versements": total_versements,
        "total_groupes": total_groupes,
        "versements_recents": versements_recents,
        "stats_groupes_admin": stats_groupes_admin,
    }

    return render(
        request,
        "cotisationtontine/dashboard.html",
        context
    )

# =====================================================
# ðŸ“Š Dashboard simple
# =====================================================

@login_required
def dashboard(request):

    action_logs = (
        ActionLog.objects
        .filter(user=request.user)
        .order_by("-date")[:10]
    )

    context = {
        "action_logs": action_logs
    }

    return render(
        request,
        "cotisationtontine/dashboard.html",
        context
    )
