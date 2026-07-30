from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from epargnecredit.models import (
    Group,
    GroupMember,
    PretDemande,
    Versement,
)


ZERO = Decimal("0")
UN_FCFA = Decimal("1")
QUATRE_DECIMALES = Decimal("0.0001")


def decimaliser(valeur) -> Decimal:
    """
    Convertit une valeur en Decimal sans exposer les calculs
    financiers aux imprécisions des nombres flottants.
    """

    if valeur in (None, ""):
        return ZERO

    return Decimal(str(valeur))


def arrondir_fcfa(valeur: Decimal) -> Decimal:
    """
    Arrondit un montant au franc CFA le plus proche.
    """

    return decimaliser(valeur).quantize(
        UN_FCFA,
        rounding=ROUND_HALF_UP,
    )


# ==========================================================
# Répartition de fin de cycle
# ==========================================================

@login_required
@require_POST
def share_cycle_view(request, group_id):
    """
    Calcule la répartition de fin de cycle du groupe.

    La répartition est proportionnelle aux cotisations validées
    de chaque membre :

        parts du membre = cotisations du membre / valeur d'une part

        montant par part = montant global / total des parts

        montant dû au membre = parts du membre × montant par part

    Le montant global comprend :
    - les cotisations validées ;
    - les intérêts générés par les prêts approuvés ou clôturés ;
    - les pénalités encaissées lorsqu'elles sont disponibles.

    Cette vue calcule et affiche la répartition. Elle ne modifie
    pas les soldes des membres et ne clôture pas automatiquement
    le cycle.
    """

    group = get_object_or_404(
        Group.objects.select_related("admin"),
        id=group_id,
    )

    # ======================================================
    # Vérification du type de groupe
    # ======================================================

    if getattr(group, "is_remboursement", False):
        messages.error(
            request,
            (
                "La répartition de fin de cycle doit être lancée "
                "depuis le groupe d'épargne principal."
            ),
        )
        return redirect(
            "epargnecredit:group_detail_remboursement",
            group_id=group.id,
        )

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
            (
                "Vous n'avez pas la permission d'effectuer "
                "le partage pour ce groupe."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Valeur d'une part
    # ======================================================

    montant_base = decimaliser(
        getattr(group, "montant_base", ZERO)
    )

    if montant_base <= ZERO:
        messages.error(
            request,
            (
                "Le montant de base, correspondant à la valeur "
                "d'une part, n'est pas défini pour ce groupe."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Filtre du cycle courant
    # ======================================================

    filtre_cycle = Q(
        member__group=group,
        statut="VALIDE",
    )

    if getattr(group, "date_reset", None):
        filtre_cycle &= Q(
            date_creation__gte=group.date_reset,
        )

    # ======================================================
    # Total des cotisations validées
    # ======================================================

    total_cotisations = (
        Versement.objects
        .filter(filtre_cycle)
        .aggregate(
            total=Coalesce(
                Sum("montant"),
                Value(
                    ZERO,
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=2,
                    ),
                ),
            )
        )
        .get("total")
        or ZERO
    )

    total_cotisations = decimaliser(
        total_cotisations
    )

    if total_cotisations <= ZERO:
        messages.warning(
            request,
            (
                "Aucune cotisation validée n'est disponible "
                "pour la répartition de ce cycle."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Total des intérêts générés par les prêts
    # ======================================================

    prets = (
        PretDemande.objects
        .filter(
            member__group=group,
            statut__in=["APPROVED", "CLOSED"],
        )
        .select_related(
            "member",
            "member__user",
        )
    )

    total_interets = ZERO
    total_penalites = ZERO

    for pret in prets:
        montant_pret = decimaliser(
            getattr(pret, "montant", ZERO)
        )

        taux_interet = decimaliser(
            getattr(pret, "interet", ZERO)
        )

        # Dans le modèle actuel, ``interet`` est utilisé comme
        # un taux en pourcentage.
        interet_pret = (
            montant_pret
            * taux_interet
            / Decimal("100")
        )

        total_interets += interet_pret

        # Compatibilité avec un éventuel champ représentant
        # directement une pénalité effectivement encaissée.
        for nom_champ in (
            "penalite_payee",
            "penalites_payees",
            "montant_penalite_payee",
        ):
            if hasattr(pret, nom_champ):
                total_penalites += decimaliser(
                    getattr(pret, nom_champ, ZERO)
                )
                break

    total_interets = arrondir_fcfa(
        total_interets
    )

    total_penalites = arrondir_fcfa(
        total_penalites
    )

    # ======================================================
    # Nombre total de parts
    # ======================================================

    total_parts = (
        total_cotisations
        / montant_base
    ).quantize(
        QUATRE_DECIMALES,
        rounding=ROUND_HALF_UP,
    )

    if total_parts <= ZERO:
        messages.error(
            request,
            "Le nombre total de parts calculé est nul.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Montant global et valeur finale d'une part
    # ======================================================

    montant_global = (
        total_cotisations
        + total_interets
        + total_penalites
    )

    montant_par_part = (
        montant_global
        / total_parts
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    # ======================================================
    # Cotisations par membre
    # ======================================================

    filtre_membres = Q(
        versements_ec__statut="VALIDE"
    )

    if getattr(group, "date_reset", None):
        filtre_membres &= Q(
            versements_ec__date_creation__gte=group.date_reset
        )

    membres = (
        GroupMember.objects
        .filter(
            group=group,
            actif=True,
        )
        .select_related("user")
        .annotate(
            cotisations_validees=Coalesce(
                Sum(
                    "versements_ec__montant",
                    filter=filtre_membres,
                ),
                Value(
                    ZERO,
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=2,
                    ),
                ),
            )
        )
        .order_by("id")
    )

    # ======================================================
    # Répartition individuelle
    # ======================================================

    repartition_lignes = []
    total_reparti = ZERO

    for membre in membres:
        cotise = decimaliser(
            membre.cotisations_validees
        )

        parts = (
            cotise / montant_base
        ).quantize(
            QUATRE_DECIMALES,
            rounding=ROUND_HALF_UP,
        )

        montant_du = (
            parts * montant_par_part
        ).quantize(
            UN_FCFA,
            rounding=ROUND_HALF_UP,
        )

        nom = (
            getattr(membre, "alias", None)
            or getattr(membre.user, "nom", None)
            or getattr(membre.user, "phone", None)
            or str(membre.user)
        )

        repartition_lignes.append(
            {
                "member": membre,
                "nom": nom,
                "cotise": arrondir_fcfa(cotise),
                "parts": parts,
                "du": montant_du,
            }
        )

        total_reparti += montant_du

    # ======================================================
    # Correction de l'écart d'arrondi
    # ======================================================

    montant_global_arrondi = arrondir_fcfa(
        montant_global
    )

    ecart_arrondi = (
        montant_global_arrondi
        - total_reparti
    )

    if repartition_lignes and ecart_arrondi != ZERO:
        # Attribuer l'écart au membre ayant le plus grand nombre
        # de parts évite que la somme affichée diffère du total.
        ligne_correction = max(
            repartition_lignes,
            key=lambda ligne: ligne["parts"],
        )

        ligne_correction["du"] += ecart_arrondi
        total_reparti += ecart_arrondi

    # Tri par montant dû décroissant
    repartition_lignes.sort(
        key=lambda ligne: ligne["du"],
        reverse=True,
    )

    # ======================================================
    # Contexte attendu par group_detail.html
    # ======================================================

    context = {
        "group": group,
        "montant_base": arrondir_fcfa(montant_base),
        "total_cotisations": arrondir_fcfa(
            total_cotisations
        ),
        "total_interets": total_interets,
        "total_penalites": total_penalites,
        "montant_global": montant_global_arrondi,
        "total_parts": total_parts,
        "montant_par_part": montant_par_part,
        "repartition_lignes": repartition_lignes,
        "total_reparti": total_reparti,
        "user_is_admin": True,
    }

    messages.success(
        request,
        "La répartition de fin de cycle a été calculée.",
    )

    return render(
        request,
        "epargnecredit/group_detail.html",
        context,
    )
