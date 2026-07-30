from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from epargnecredit.models import ActionLog, Group, GroupMember


def _user_can_access_group(user, group: Group) -> bool:
    """
    Vérifie si l'utilisateur peut consulter les données du groupe.
    """

    return (
        user == group.admin
        or GroupMember.objects.filter(
            group=group,
            user=user,
            actif=True,
        ).exists()
        or getattr(user, "is_super_admin", False)
        or getattr(user, "is_superuser", False)
    )


# ==========================================================
# Historique des cycles
# ==========================================================

@login_required
def historique_cycles_view(
    request: HttpRequest,
    group_id: int,
) -> HttpResponse:
    """
    Affiche l'historique des cycles terminés d'un groupe.

    La vue reste compatible avec un projet dans lequel le modèle
    ``Cycle`` n'existe pas encore. Dans ce cas, la page est rendue
    avec une liste vide.
    """

    group = get_object_or_404(
        Group.objects.select_related("admin"),
        id=group_id,
    )

    # ======================================================
    # Vérification de l'accès
    # ======================================================

    if not _user_can_access_group(request.user, group):
        messages.error(
            request,
            (
                "Vous n'avez pas l'autorisation de consulter "
                "l'historique de ce groupe."
            ),
        )
        return redirect("epargnecredit:group_list")

    # ======================================================
    # Chargement dynamique du modèle Cycle
    # ======================================================

    try:
        Cycle = apps.get_model(
            "epargnecredit",
            "Cycle",
        )
    except LookupError:
        Cycle = None

    anciens_cycles = []

    if Cycle is not None:
        queryset = (
            Cycle.objects
            .filter(group=group)
            .exclude(date_fin__isnull=True)
            .order_by("-date_debut")
        )

        # Cette relation existe dans la version actuelle du projet.
        # Si elle est absente dans une autre version, Django lèvera
        # une erreur seulement lors de l'évaluation du queryset.
        try:
            queryset = queryset.prefetch_related(
                "etapes__tirage__beneficiaire__user"
            )
            anciens_cycles = list(queryset)
        except Exception:
            anciens_cycles = list(
                Cycle.objects
                .filter(group=group)
                .exclude(date_fin__isnull=True)
                .order_by("-date_debut")
            )

    context = {
        "group": group,
        "anciens_cycles": anciens_cycles,
        "cycle_model_disponible": Cycle is not None,
    }

    return render(
        request,
        "epargnecredit/historique_cycles.html",
        context,
    )


# ==========================================================
# Historique général des actions
# ==========================================================

@login_required
def historique_actions_view(
    request: HttpRequest,
) -> HttpResponse:
    """
    Affiche les actions enregistrées dans ``ActionLog``.

    - Un super-administrateur ou superutilisateur voit tous les logs.
    - Un administrateur de groupe voit les logs de ses groupes.
    - Un membre voit les logs des groupes auxquels il appartient.
    """

    user = request.user

    logs = (
        ActionLog.objects
        .select_related(
            "user",
            "group",
        )
        .order_by("-date")
    )

    if not (
        getattr(user, "is_super_admin", False)
        or getattr(user, "is_superuser", False)
    ):
        logs = (
            logs
            .filter(
                group__in=Group.objects.filter(
                    admin=user,
                )
                | Group.objects.filter(
                    membres_ec=user,
                )
            )
            .distinct()
        )

    return render(
        request,
        "epargnecredit/historique_actions.html",
        {
            "logs": logs,
        },
    )
