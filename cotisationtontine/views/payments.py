from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cotisationtontine.models import GroupMember, Versement


# ==========================================================
# INITIATION D'UN VERSEMENT
# ==========================================================

@login_required
@transaction.atomic
def initier_versement(request, member_id):
    member = get_object_or_404(
        GroupMember.objects
        .select_related("group", "user"),
        id=member_id,
    )

    group = member.group
    group.refresh_from_db()

    # ======================================================
    # SÉCURITÉ
    # ======================================================

    user_is_admin = (
        request.user == group.admin
        or request.user.is_superuser
    )

    if not user_is_admin and request.user != member.user:
        messages.error(
            request,
            "Vous ne pouvez verser que pour vous-même.",
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # VÉRIFIER SI LE CYCLE EST TERMINÉ
    # ======================================================

    membres_actifs = group.membres.filter(
        actif=True,
        exit_liste=False,
    )

    gagnants_ids = (
        group.tirages
        .filter(cycle_number=group.cycle_numero)
        .values_list("gagnant_id", flat=True)
    )

    membres_restants = membres_actifs.exclude(
        id__in=gagnants_ids,
    )

    if not membres_restants.exists():
        messages.error(
            request,
            "Le cycle est terminé. Veuillez le réinitialiser.",
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # BLOQUER UN DOUBLE PAIEMENT VALIDÉ
    # ======================================================

    total_valide = (
        Versement.objects
        .filter(
            member=member,
            statut="VALIDE",
            cycle=group.cycle_numero,
            tour=group.tour_actuel,
        )
        .aggregate(total=Sum("montant"))["total"]
        or Decimal("0")
    )

    montant_max = group.montant_base or Decimal("0")
    reste_valide = montant_max - total_valide

    if reste_valide <= 0:
        messages.success(
            request,
            (
                "Vous avez déjà complété le paiement "
                f"pour le tour {group.tour_actuel}."
            ),
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # CALCUL DU RESTE À PAYER
    # ======================================================

    versements_tour = member.versements.filter(
        statut__in=["EN_ATTENTE", "VALIDE"],
        cycle=group.cycle_numero,
        tour=group.tour_actuel,
    )

    total_actuel = (
        versements_tour
        .aggregate(total=Sum("montant"))["total"]
        or Decimal("0")
    )

    reste = montant_max - total_actuel

    # ======================================================
    # AFFICHAGE DU FORMULAIRE
    # ======================================================

    if request.method == "GET":
        frais = (
            reste * Decimal("0.02")
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

        total = reste + frais

        return render(
            request,
            "cotisationtontine/initier_versement.html",
            {
                "member": member,
                "group": group,
                "montant_base": montant_max,
                "reste": reste,
                "frais": frais,
                "total": total,
                "tour": group.tour_actuel,
            },
        )

    # ======================================================
    # TRAITEMENT DU FORMULAIRE
    # ======================================================

    montant_raw = (
        request.POST.get("montant") or ""
    ).replace(",", ".").strip()

    methode = (
        request.POST.get("methode") or ""
    ).strip().upper()

    preuve = request.FILES.get("preuve")

    try:
        montant = Decimal(montant_raw)
    except (InvalidOperation, TypeError, ValueError):
        messages.error(
            request,
            "Montant invalide.",
        )
        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member_id,
        )

    if montant <= 0:
        messages.error(
            request,
            "Le montant doit être supérieur à zéro.",
        )
        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member_id,
        )

    montant = montant.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    if reste <= 0:
        messages.warning(
            request,
            "Le montant du tour est déjà atteint.",
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    if montant > reste:
        messages.error(
            request,
            f"Dépassement : il reste {reste} FCFA à payer.",
        )
        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member_id,
        )

    # ======================================================
    # VALIDATION DE LA MÉTHODE DE PAIEMENT
    # ======================================================

    methodes_autorisees = {
        "WAVE",
        "OM",
        "CAISSE",
    }

    if methode not in methodes_autorisees:
        messages.error(
            request,
            "Méthode de paiement invalide.",
        )
        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member_id,
        )

    # ======================================================
    # CALCUL DES FRAIS
    # ======================================================

    frais = (
        montant * Decimal("0.02")
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    # ======================================================
    # CRÉATION DU VERSEMENT
    # ======================================================

    versement = Versement.objects.create(
        member=member,
        montant=montant,
        frais=frais,
        methode=methode,
        preuve=preuve,
        statut="EN_ATTENTE",
        cycle=group.cycle_numero,
        tour=group.tour_actuel,
    )

    print("VERSEMENT CRÉÉ ID =", versement.id)

    messages.success(
        request,
        (
            f"Paiement de {montant} FCFA envoyé via {methode}. "
            "Il est en attente de validation."
        ),
    )

    return redirect(
        "cotisationtontine:group_detail",
        group_id=group.id,
    )


# ==========================================================
# VALIDATION ADMINISTRATEUR
# ==========================================================

@login_required
@require_POST
@transaction.atomic
def valider_versement(request, versement_id):
    versement = get_object_or_404(
        Versement.objects
        .select_for_update()
        .select_related("member__group"),
        id=versement_id,
    )

    group = versement.member.group

    if request.user != group.admin and not request.user.is_superuser:
        messages.error(
            request,
            "Accès refusé.",
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    if versement.statut == "VALIDE":
        messages.info(
            request,
            "Ce versement est déjà validé.",
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    if versement.statut == "REFUSE":
        messages.error(
            request,
            (
                "Ce versement a déjà été refusé. "
                "Il ne peut pas être validé directement."
            ),
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    versement.statut = "VALIDE"
    versement.valide_par = request.user
    versement.date_validation = timezone.now()

    versement.save(
        update_fields=[
            "statut",
            "valide_par",
            "date_validation",
        ],
    )

    messages.success(
        request,
        "Versement validé avec succès.",
    )

    return redirect(
        "cotisationtontine:group_detail",
        group_id=group.id,
    )


# ==========================================================
# REFUS ADMINISTRATEUR
# ==========================================================

@login_required
@require_POST
@transaction.atomic
def refuser_versement(request, versement_id):
    versement = get_object_or_404(
        Versement.objects
        .select_for_update()
        .select_related("member__group"),
        id=versement_id,
    )

    group = versement.member.group

    if request.user != group.admin and not request.user.is_superuser:
        messages.error(
            request,
            "Accès refusé.",
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    if versement.statut == "REFUSE":
        messages.info(
            request,
            "Ce versement est déjà refusé.",
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    if versement.statut == "VALIDE":
        messages.error(
            request,
            (
                "Ce versement est déjà validé. "
                "Il ne peut pas être refusé."
            ),
        )
        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    versement.statut = "REFUSE"
    versement.valide_par = request.user
    versement.date_validation = timezone.now()

    versement.save(
        update_fields=[
            "statut",
            "valide_par",
            "date_validation",
        ],
    )

    messages.success(
        request,
        "Versement refusé.",
    )

    return redirect(
        "cotisationtontine:group_detail",
        group_id=group.id,
    )