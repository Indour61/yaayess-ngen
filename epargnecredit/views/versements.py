from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from epargnecredit.models import GroupMember, Versement
from epargnecredit.utils_notification import notifier_validation_versement
from epargnecredit.utils_pdf import generer_recu_pdf


# ==========================================================
# Déclaration d'un versement en caisse
# ==========================================================

@login_required
@transaction.atomic
def initier_versement(request, member_id):
    """
    Enregistre un versement manuel en caisse.

    Le versement est créé avec le statut EN_ATTENTE et devra
    être validé par l'administrateur du groupe.

    Le membre concerné, l'administrateur du groupe, un
    super-administrateur ou un superutilisateur peut initier
    le versement.
    """

    member = get_object_or_404(
        GroupMember.objects.select_related(
            "group",
            "group__admin",
            "user",
        ),
        id=member_id,
        actif=True,
    )

    group = member.group

    # ======================================================
    # Vérification des permissions
    # ======================================================

    has_access = (
        request.user == member.user
        or request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_access:
        messages.error(
            request,
            (
                "Vous n'avez pas l'autorisation "
                "d'effectuer ce versement."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Affichage du formulaire
    # ======================================================

    if request.method == "GET":
        return render(
            request,
            "epargnecredit/initier_versement.html",
            {
                "member": member,
                "group": group,
            },
        )

    # ======================================================
    # Lecture et validation du montant
    # ======================================================

    montant_brut = request.POST.get("montant", "")

    montant_str = (
        str(montant_brut)
        .strip()
        .replace("\\u00a0", "")
        .replace(" ", "")
        .replace(",", ".")
    )

    try:
        if not montant_str:
            raise InvalidOperation

        montant = Decimal(montant_str)

    except (InvalidOperation, ValueError, TypeError):
        messages.error(
            request,
            "Veuillez saisir un montant valide.",
        )
        return redirect(
            "epargnecredit:initier_versement",
            member_id=member.id,
        )

    if montant <= 0:
        messages.error(
            request,
            "Le montant doit être supérieur à zéro.",
        )
        return redirect(
            "epargnecredit:initier_versement",
            member_id=member.id,
        )

    if montant != montant.to_integral_value():
        messages.error(
            request,
            "Le montant doit être un nombre entier en FCFA.",
        )
        return redirect(
            "epargnecredit:initier_versement",
            member_id=member.id,
        )

    montant = montant.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    # ======================================================
    # Frais plateforme YaayESS : 1 %
    # ======================================================

    frais = (
        montant * Decimal("0.01")
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    # ======================================================
    # Création du versement
    # ======================================================

    Versement.objects.create(
        member=member,
        montant=montant,
        frais=frais,
        methode="CAISSE",
        statut="EN_ATTENTE",
    )

    messages.success(
        request,
        (
            f"Versement de {montant:,.0f} FCFA enregistré. "
            f"Frais plateforme : {frais:,.0f} FCFA. "
            "Le versement est en attente de validation."
        ),
    )

    return redirect(
        "epargnecredit:group_detail",
        group_id=group.id,
    )


# ==========================================================
# Validation d'un versement
# ==========================================================

@login_required
@require_POST
@transaction.atomic
def valider_versement(request, versement_id):
    """
    Valide un versement en attente.

    Seul l'administrateur du groupe, un super-administrateur
    ou un superutilisateur peut valider un versement.
    """

    versement = get_object_or_404(
        Versement.objects
        .select_for_update()
        .select_related(
            "member",
            "member__group",
            "member__group__admin",
            "member__user",
        ),
        id=versement_id,
    )

    group = versement.member.group

    # ======================================================
    # Vérification des permissions
    # ======================================================

    has_permission = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_permission:
        messages.error(
            request,
            "Accès refusé.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Protection contre une double validation
    # ======================================================

    if versement.statut != "EN_ATTENTE":
        messages.warning(
            request,
            "Ce versement a déjà été traité.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Validation métier centralisée
    # ======================================================

    versement.valider(request.user)

    # ======================================================
    # Génération du reçu PDF
    # ======================================================

    try:
        generer_recu_pdf(versement)
    except Exception as exc:
        print(
            "Erreur lors de la génération du reçu PDF "
            f"du versement {versement.id} : {exc}"
        )

    # ======================================================
    # Notification du membre
    # ======================================================

    try:
        notifier_validation_versement(
            versement.member.user,
            versement.montant,
        )
    except Exception as exc:
        print(
            "Erreur lors de la notification du versement "
            f"{versement.id} : {exc}"
        )

    messages.success(
        request,
        (
            f"Versement de {versement.montant:,.0f} FCFA "
            "validé avec succès. Le reçu a été généré."
        ),
    )

    return redirect(
        "epargnecredit:group_detail",
        group_id=group.id,
    )


# ==========================================================
# Refus d'un versement
# ==========================================================

@login_required
@require_POST
@transaction.atomic
def refuser_versement(request, versement_id):
    """
    Refuse un versement en attente.

    Seul l'administrateur du groupe, un super-administrateur
    ou un superutilisateur peut refuser un versement.
    """

    versement = get_object_or_404(
        Versement.objects
        .select_for_update()
        .select_related(
            "member",
            "member__group",
            "member__group__admin",
            "member__user",
        ),
        id=versement_id,
    )

    group = versement.member.group

    # ======================================================
    # Vérification des permissions
    # ======================================================

    has_permission = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_permission:
        messages.error(
            request,
            "Accès refusé.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Protection contre un double traitement
    # ======================================================

    if versement.statut != "EN_ATTENTE":
        messages.warning(
            request,
            "Ce versement a déjà été traité.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Refus métier centralisé
    # ======================================================

    versement.refuser(request.user)

    messages.success(
        request,
        (
            f"Le versement de {versement.montant:,.0f} FCFA "
            "a été refusé."
        ),
    )

    return redirect(
        "epargnecredit:group_detail",
        group_id=group.id,
    )
