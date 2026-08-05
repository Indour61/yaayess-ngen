from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cotisationtontine.models import GroupMember, Versement

# ==========================================
# DECLARATION VERSEMENT CAISSE
# ==========================================

@login_required
@transaction.atomic
def initier_versement(request, member_id):

    member = get_object_or_404(
        GroupMember.objects.select_related("group", "user"),
        id=member_id
    )

    group = member.group
    group.refresh_from_db()

    # =====================================================
    # ðŸ”’ SÃ‰CURITÃ‰
    # =====================================================

    user_is_admin = (
        request.user == group.admin
        or request.user.is_superuser
    )

    if not user_is_admin and request.user != member.user:
        messages.error(request, "âŒ Vous ne pouvez verser que pour vous-mÃªme.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # =====================================================
    # ðŸ”¥ VÃ‰RIFIER SI CYCLE TERMINÃ‰
    # =====================================================

    membres_actifs = group.membres.filter(actif=True, exit_liste=False)

    gagnants_ids = group.tirages.filter(
        cycle_number=group.cycle_numero
    ).values_list("gagnant_id", flat=True)

    membres_restants = membres_actifs.exclude(id__in=gagnants_ids)

    if not membres_restants.exists():
        messages.error(request, "âŒ Le cycle est terminÃ©. Veuillez rÃ©initialiser.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # =====================================================
    # ðŸ”¥ BLOQUER DOUBLE PAIEMENT VALIDÃ‰
    # =====================================================

    # ðŸ”¥ TOTAL dÃ©jÃ  versÃ© (VALIDÃ‰ uniquement)
    total_valide = Versement.objects.filter(
        member=member,
        statut="VALIDE",
        cycle=group.cycle_numero,
        tour=group.tour_actuel
    ).aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    # ðŸ”¥ Montant max Ã  atteindre
    montant_max = group.montant_base or Decimal("0")

    # ðŸ”¥ Calcul du reste
    reste = montant_max - total_valide

    # ðŸ”’ Bloquer si dÃ©jÃ  complet
    if reste <= 0:
        messages.success(
            request,
            f"âœ… Vous avez dÃ©jÃ  complÃ©tÃ© le paiement pour le tour {group.tour_actuel}."
        )
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # =====================================================
    # ðŸ”¥ CALCUL DU RESTE Ã€ PAYER
    # =====================================================

    versements_tour = member.versements.filter(
        statut__in=["EN_ATTENTE", "VALIDE"],
        tour=group.tour_actuel,
        cycle=group.cycle_numero
    )

    total_actuel = versements_tour.aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    montant_max = group.montant_base or Decimal("0")
    reste = montant_max - total_actuel

    # =====================================================
    # GET â†’ AFFICHAGE PAGE
    # =====================================================

    if request.method == "GET":

        frais = (reste * Decimal("0.02")).quantize(Decimal("1"))
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
                "tour": group.tour_actuel
            }
        )

    # =====================================================
    # POST â†’ TRAITEMENT
    # =====================================================

    montant_raw = (request.POST.get("montant") or "").replace(",", ".").strip()
    methode = request.POST.get("methode")
    preuve = request.FILES.get("preuve")

    # ðŸ”’ validation montant
    try:
        montant = Decimal(montant_raw)
    except Exception:
        messages.error(request, "âŒ Montant invalide.")
        return redirect("cotisationtontine:initier_versement", member_id=member_id)

    if montant <= 0:
        messages.error(request, "âŒ Le montant doit Ãªtre supÃ©rieur Ã  0.")
        return redirect("cotisationtontine:initier_versement", member_id=member_id)

    montant = montant.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # ðŸ”’ dÃ©jÃ  complet
    if reste <= 0:
        messages.warning(request, "âœ… Montant dÃ©jÃ  atteint pour ce tour.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # ðŸ”’ dÃ©passement
    if montant > reste:
        messages.error(request, f"âŒ DÃ©passement ! Il reste {reste} FCFA.")
        return redirect("cotisationtontine:initier_versement", member_id=member_id)

    # =====================================================
    # ðŸ”’ VALIDATION MÃ‰THODE
    # =====================================================

    if methode not in ["WAVE", "OM", "CAISSE"]:
        messages.error(request, "âŒ MÃ©thode de paiement invalide.")
        return redirect("cotisationtontine:initier_versement", member_id=member_id)

    # =====================================================
    # ðŸ’° FRAIS
    # =====================================================

    frais = (montant * Decimal("0.02")).quantize(Decimal("1"))

    # =====================================================
    # ðŸ’° CRÃ‰ATION VERSEMENT
    # =====================================================

    versement = Versement.objects.create(
        member=member,
        montant=montant,
        frais=frais,
        methode=methode,
        preuve=preuve,
        statut="EN_ATTENTE",
        tour=group.tour_actuel,
        cycle=group.cycle_numero
    )

    print("âœ… VERSEMENT CRÃ‰Ã‰ ID =", versement.id)

    # =====================================================
    # ðŸ”¥ MESSAGE UX
    # =====================================================

    messages.success(
        request,
        f"â³ Paiement de {montant} FCFA envoyÃ© via {methode}. En attente de validation."
    )

    return redirect("cotisationtontine:group_detail", group_id=group.id)

# ==========================================
# VALIDATION ADMIN
# ==========================================

@login_required
@transaction.atomic
def valider_versement(request, versement_id):

    versement = get_object_or_404(
        Versement.objects.select_related("member__group"),
        id=versement_id
    )
    group = versement.member.group

    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "AccÃ¨s refusÃ©.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    versement.statut = "VALIDE"
    versement.valide_par = request.user
    versement.date_validation = timezone.now()
    versement.save()

    messages.success(request, "Versement validÃ© avec succÃ¨s.")
    return redirect("cotisationtontine:group_detail", group_id=group.id)


# ==========================================
# REFUSER VERSEMENT
# ==========================================

@login_required
@transaction.atomic
def refuser_versement(request, versement_id):

    versement = get_object_or_404(
        Versement.objects.select_related("member__group"),
        id=versement_id
    )
    group = versement.member.group

    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "AccÃ¨s refusÃ©.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    versement.statut = "REFUSE"
    versement.valide_par = request.user
    versement.date_validation = timezone.now()
    versement.save()

    messages.success(request, "Versement refusÃ©.")
    return redirect("cotisationtontine:group_detail", group_id=group.id)
