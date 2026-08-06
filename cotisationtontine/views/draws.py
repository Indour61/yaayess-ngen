import random

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from cotisationtontine.models import Group, Tirage, Versement


# ==========================================================
# TIRAGE AU SORT
# ==========================================================

@login_required
@require_POST
@transaction.atomic
def tirage_au_sort_view(request, group_id):
    """
    Effectue le tirage d'un bénéficiaire pour le tour courant.

    Le montant attribué au gagnant correspond uniquement à la somme
    des versements validés du cycle et du tour en cours.
    """

    # Verrouille le groupe pendant toute l'opération afin
    # d'empêcher deux tirages simultanés.
    group = get_object_or_404(
        Group.objects.select_for_update(),
        id=group_id,
    )

    # ======================================================
    # CONTRÔLE DES PERMISSIONS
    # ======================================================

    if request.user != group.admin and not request.user.is_superuser:
        return JsonResponse(
            {
                "error": "Accès non autorisé.",
            },
            status=403,
        )

    membres_actifs = group.membres.filter(
        actif=True,
        exit_liste=False,
    )

    if not membres_actifs.exists():
        return JsonResponse(
            {
                "error": "Aucun membre actif dans ce groupe.",
            },
            status=400,
        )

    # ======================================================
    # CYCLE ET TOUR COURANTS
    # ======================================================

    cycle_en_cours = group.cycle_numero
    tour_en_cours = group.tour_actuel

    gagnants_ids = (
        group.tirages
        .filter(cycle_number=cycle_en_cours)
        .values_list("gagnant_id", flat=True)
    )

    membres_restants = membres_actifs.exclude(
        id__in=gagnants_ids,
    )

    # ======================================================
    # CYCLE DÉJÀ TERMINÉ
    # ======================================================

    if not membres_restants.exists():
        group.cycle_termine = True
        group.is_active = False

        group.save(
            update_fields=[
                "cycle_termine",
                "is_active",
            ],
        )

        if group.auto_reset:
            group.reset_cycle()

            return JsonResponse(
                {
                    "reset": True,
                    "message": (
                        "Le cycle précédent est terminé. "
                        "Un nouveau cycle a été démarré."
                    ),
                    "cycle": group.cycle_numero,
                },
            )

        return JsonResponse(
            {
                "cycle_termine": True,
                "message": (
                    "Le cycle est terminé. "
                    "Un nouveau cycle doit être démarré."
                ),
                "cycle": cycle_en_cours,
            },
            status=400,
        )

    # ======================================================
    # FILTRE STRICT DES VERSEMENTS VALIDÉS
    # ======================================================

    versements_valides_q = Q(
        member__group=group,
        statut="VALIDE",
        cycle=cycle_en_cours,
        tour=tour_en_cours,
    )

    # ======================================================
    # VÉRIFIER QUE TOUS LES MEMBRES ONT PAYÉ
    # ======================================================

    membres_non_a_jour = []

    for membre in membres_actifs:
        a_paye = Versement.objects.filter(
            versements_valides_q,
            member=membre,
        ).exists()

        if not a_paye:
            nom_membre = (
                membre.alias
                or getattr(membre.user, "username", "")
                or getattr(membre.user, "phone", "")
                or "Membre"
            )

            membres_non_a_jour.append(nom_membre)

    if membres_non_a_jour:
        return JsonResponse(
            {
                "error": (
                    "Tous les membres doivent avoir un versement "
                    "validé avant le tirage."
                ),
                "non_payes": membres_non_a_jour,
            },
            status=400,
        )

    # ======================================================
    # VÉRIFIER LES VERSEMENTS EN ATTENTE
    # ======================================================

    versements_en_attente = Versement.objects.filter(
        member__group=group,
        statut="EN_ATTENTE",
        cycle=cycle_en_cours,
        tour=tour_en_cours,
    )

    if versements_en_attente.exists():
        return JsonResponse(
            {
                "error": (
                    "Tous les versements du cycle et du tour en cours "
                    "doivent être validés avant le tirage."
                ),
            },
            status=400,
        )

    # ======================================================
    # MEMBRES ÉLIGIBLES
    # ======================================================

    membres_eligibles = list(membres_restants)

    if not membres_eligibles:
        return JsonResponse(
            {
                "error": "Aucun membre éligible pour ce tirage.",
            },
            status=400,
        )

    # ======================================================
    # CALCUL DU MONTANT DU TOUR
    # ======================================================

    montant_total = (
        Versement.objects
        .filter(versements_valides_q)
        .aggregate(total=Sum("montant"))
        .get("total")
        or 0
    )

    if montant_total <= 0:
        return JsonResponse(
            {
                "error": (
                    "Le montant total des versements validés "
                    "du tour est nul."
                ),
            },
            status=400,
        )

    # ======================================================
    # TIRAGE
    # ======================================================

    gagnant = random.choice(membres_eligibles)

    tirage = Tirage.objects.create(
        group=group,
        gagnant=gagnant,
        montant=montant_total,
        cycle_number=cycle_en_cours,
        tour=tour_en_cours,
    )

    # ======================================================
    # MISE À JOUR DU GAGNANT ET DU GROUPE
    # ======================================================

    gagnant.a_recu = True
    gagnant.save(
        update_fields=[
            "a_recu",
        ],
    )

    group.prochain_gagnant = gagnant
    group.save(
        update_fields=[
            "prochain_gagnant",
        ],
    )

    # Passage au tour suivant.
    group.reset_apres_tirage()

    # ======================================================
    # VÉRIFIER SI LE CYCLE VIENT DE SE TERMINER
    # ======================================================

    gagnants_ids = (
        group.tirages
        .filter(cycle_number=cycle_en_cours)
        .values_list("gagnant_id", flat=True)
    )

    membres_restants_apres_tirage = membres_actifs.exclude(
        id__in=gagnants_ids,
    )

    cycle_termine = not membres_restants_apres_tirage.exists()

    if cycle_termine:
        group.cycle_termine = True
        group.is_active = False

        group.save(
            update_fields=[
                "cycle_termine",
                "is_active",
            ],
        )

    # ======================================================
    # NOM DU GAGNANT
    # ======================================================

    nom_gagnant = (
        gagnant.alias
        or getattr(gagnant.user, "username", "")
        or getattr(gagnant.user, "phone", "")
        or "Membre"
    )

    return JsonResponse(
        {
            "success": True,
            "tirage_id": tirage.id,
            "gagnant": nom_gagnant,
            "montant": montant_total,
            "cycle": cycle_en_cours,
            "tour": tour_en_cours,
            "cycle_termine": cycle_termine,
            "membres_restants": (
                membres_restants_apres_tirage.count()
            ),
        },
    )


# ==========================================================
# RÉSULTAT DU TIRAGE
# ==========================================================

def tirage_resultat_view(request, group_id, token=None):
    group = get_object_or_404(
        Group,
        id=group_id,
    )

    # ======================================================
    # CONTRÔLE D'ACCÈS
    # ======================================================

    is_member = False
    is_admin = False

    if request.user.is_authenticated:
        is_member = group.membres.filter(
            user=request.user,
        ).exists()

        is_admin = (
            request.user == group.admin
            or request.user.is_superuser
            or getattr(
                request.user,
                "is_super_admin",
                False,
            )
        )

    if not is_member and not is_admin:
        access_token = str(
            getattr(
                group,
                "access_token",
                "",
            )
        )

        if not token or access_token != str(token):
            return HttpResponseForbidden(
                "Accès refusé.",
            )

    # ======================================================
    # TIRAGES
    # ======================================================

    tirages = (
        group.tirages
        .select_related("gagnant__user")
        .order_by("-date_tirage")
    )

    dernier_tirage = tirages.first()

    gagnant = None
    montant_total = 0
    cycle_actuel = group.cycle_numero
    tour_affiche = group.tour_actuel

    if dernier_tirage:
        gagnant = dernier_tirage.gagnant
        cycle_actuel = (
            dernier_tirage.cycle_number
            or group.cycle_numero
        )
        montant_total = dernier_tirage.montant
        tour_affiche = dernier_tirage.tour

    # ======================================================
    # ÉTAT DU CYCLE
    # ======================================================

    membres_actifs = group.membres.filter(
        actif=True,
        exit_liste=False,
    )

    gagnants_ids = (
        tirages
        .filter(cycle_number=cycle_actuel)
        .values_list("gagnant_id", flat=True)
    )

    membres_restants = membres_actifs.exclude(
        id__in=gagnants_ids,
    )

    cycle_termine = not membres_restants.exists()
    tirage_possible = membres_restants.exists()

    total_membres = membres_actifs.count()
    restants = membres_restants.count()
    termines = total_membres - restants

    progress = (
        int(
            (termines / total_membres) * 100
        )
        if total_membres > 0
        else 0
    )

    context = {
        "group": group,
        "tirages": tirages,
        "gagnant": gagnant,
        "montant_total": montant_total,
        "tirage_possible": tirage_possible,
        "cycle_actuel": cycle_actuel,
        "cycle_termine": cycle_termine,
        "nb_restants": restants,
        "progress": progress,
        "tour_affiche": tour_affiche,
    }

    return render(
        request,
        "cotisationtontine/tirage_resultat.html",
        context,
    )


# ==========================================================
# MEMBRES ÉLIGIBLES POUR UN TIRAGE
# ==========================================================

def membres_eligibles_pour_tirage(group):
    """
    Retourne les membres actifs qui n'ont pas encore gagné
    pendant le cycle courant.
    """

    membres_actifs = group.membres.filter(
        actif=True,
        exit_liste=False,
    )

    if not membres_actifs.exists():
        return membres_actifs

    gagnants_ids = (
        group.tirages
        .filter(cycle_number=group.cycle_numero)
        .values_list("gagnant_id", flat=True)
    )

    return membres_actifs.exclude(
        id__in=gagnants_ids,
    )