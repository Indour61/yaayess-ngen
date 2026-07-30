import calendar
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from epargnecredit.models import (
    Group,
    GroupMember,
    PretDemande,
    PretRemboursement,
)


def ajouter_mois(date_depart: date, nombre_mois: int) -> date:
    """
    Ajoute un nombre de mois à une date sans dépendance externe.

    Exemple :
    le 31 janvier augmenté d'un mois devient le dernier jour
    du mois de février.
    """

    index_mois = date_depart.month - 1 + nombre_mois
    annee = date_depart.year + index_mois // 12
    mois = index_mois % 12 + 1

    dernier_jour = calendar.monthrange(annee, mois)[1]
    jour = min(date_depart.day, dernier_jour)

    return date(annee, mois, jour)


# ==========================================================
# Détail du groupe de remboursement
# ==========================================================

@login_required
def group_detail_remboursement(request, group_id):
    """
    Affiche le groupe de remboursement associé à un groupe
    d'épargne et calcule la situation de chaque emprunteur.
    """

    group = get_object_or_404(
        Group.objects.select_related(
            "admin",
            "parent_group",
        ),
        pk=group_id,
        is_remboursement=True,
    )

    parent = group.parent_group

    # ======================================================
    # Vérification du groupe parent
    # ======================================================

    if parent is None:
        messages.error(
            request,
            "Le groupe d'épargne associé est introuvable.",
        )
        return redirect("epargnecredit:group_list")

    # ======================================================
    # Vérification de l'accès
    # ======================================================

    has_access = (
        request.user == group.admin
        or request.user == parent.admin
        or GroupMember.objects.filter(
            group=group,
            user=request.user,
            actif=True,
        ).exists()
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_access:
        messages.error(
            request,
            "Accès non autorisé.",
        )
        return redirect("epargnecredit:group_list")

    # ======================================================
    # Membres du groupe de remboursement
    # ======================================================

    membres = list(
        GroupMember.objects
        .select_related("user")
        .filter(
            group=group,
            actif=True,
        )
        .order_by("user__nom", "id")
    )

    # ======================================================
    # Totaux initiaux
    # ======================================================

    totals = {
        "total_verse": Decimal("0"),
        "montant_prete_plus_interet": Decimal("0"),
        "mensualite": Decimal("0"),
        "penalites": Decimal("0"),
        "reste_a_rembourser": Decimal("0"),
    }

    if not membres:
        return render(
            request,
            "epargnecredit/group_detail_remboursement.html",
            {
                "group": group,
                "parent_group": parent,
                "membres": [],
                "totals": totals,
            },
        )

    user_ids = [
        membre.user_id
        for membre in membres
    ]

    # ======================================================
    # Prêts des membres dans le groupe parent
    # ======================================================

    prets = list(
        PretDemande.objects
        .filter(
            member__group=parent,
            member__user_id__in=user_ids,
            statut__in=["APPROVED", "CLOSED"],
        )
        .select_related(
            "member",
            "member__user",
        )
        .order_by(
            "member__user_id",
            "-created_at",
        )
    )

    # Conserver le prêt le plus récent de chaque utilisateur
    prets_map = {}

    for pret in prets:
        prets_map.setdefault(
            pret.member.user_id,
            pret,
        )

    # ======================================================
    # Remboursements validés seulement
    # ======================================================

    remboursements = (
        PretRemboursement.objects
        .filter(
            pret__in=prets,
            statut="VALIDE",
        )
        .values("pret_id")
        .annotate(total=Sum("montant"))
    )

    remboursements_map = {
        remboursement["pret_id"]:
            remboursement["total"] or Decimal("0")
        for remboursement in remboursements
    }

    aujourd_hui = timezone.localdate()

    # ======================================================
    # Calculs par membre
    # ======================================================

    for membre in membres:
        pret = prets_map.get(membre.user_id)

        # Le template peut accéder directement au prêt
        membre.pret = pret

        if pret is None:
            membre.total_verse = Decimal("0")
            membre.montant_prete_plus_interet = Decimal("0")
            membre.mensualite = Decimal("0")
            membre.penalites = Decimal("0")
            membre.reste_a_rembourser = Decimal("0")
            membre.nombre_echeances_en_retard = 0
            membre.montant_en_retard = Decimal("0")
            continue

        total_rembourse = Decimal(
            str(
                remboursements_map.get(
                    pret.id,
                    Decimal("0"),
                )
            )
        )

        total_du = Decimal(
            str(pret.total_a_rembourser or 0)
        )

        mensualite = Decimal(
            str(pret.mensualite or 0)
        )

        taux_penalite = Decimal(
            str(pret.penalite or 0)
        )

        # ==================================================
        # Nombre d'échéances réellement dépassées
        # ==================================================

        nombre_echeances_en_retard = 0

        if pret.debut_remboursement and pret.nb_mois:
            for numero_echeance in range(pret.nb_mois):
                date_echeance = ajouter_mois(
                    pret.debut_remboursement,
                    numero_echeance,
                )

                if date_echeance < aujourd_hui:
                    nombre_echeances_en_retard += 1

        # ==================================================
        # Montant qui aurait déjà dû être remboursé
        # ==================================================

        montant_theorique_echu = min(
            mensualite * nombre_echeances_en_retard,
            total_du,
        )

        montant_en_retard = max(
            montant_theorique_echu - total_rembourse,
            Decimal("0"),
        )

        # ==================================================
        # Pénalité appliquée seulement au montant en retard
        # ==================================================

        if montant_en_retard > 0 and taux_penalite > 0:
            montant_penalite = (
                montant_en_retard
                * taux_penalite
                / Decimal("100")
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        else:
            montant_penalite = Decimal("0")

        reste_hors_penalite = max(
            total_du - total_rembourse,
            Decimal("0"),
        )

        reste_total = (
            reste_hors_penalite
            + montant_penalite
        )

        # ==================================================
        # Fermeture automatique du prêt
        # ==================================================

        if (
            pret.statut != "CLOSED"
            and reste_hors_penalite <= 0
            and montant_penalite <= 0
        ):
            pret.statut = "CLOSED"
            pret.save(update_fields=["statut"])

        # ==================================================
        # Valeurs utilisées par le template
        # ==================================================

        membre.total_verse = total_rembourse
        membre.montant_prete_plus_interet = total_du
        membre.mensualite = mensualite
        membre.penalites = montant_penalite
        membre.reste_a_rembourser = reste_total
        membre.nombre_echeances_en_retard = (
            nombre_echeances_en_retard
        )
        membre.montant_en_retard = montant_en_retard

        # ==================================================
        # Totaux généraux
        # ==================================================

        totals["total_verse"] += total_rembourse
        totals["montant_prete_plus_interet"] += total_du
        totals["mensualite"] += mensualite
        totals["penalites"] += montant_penalite
        totals["reste_a_rembourser"] += reste_total

    # ======================================================
    # Arrondi des totaux en FCFA
    # ======================================================

    for cle in totals:
        totals[cle] = totals[cle].quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

    return render(
        request,
        "epargnecredit/group_detail_remboursement.html",
        {
            "group": group,
            "parent_group": parent,
            "membres": membres,
            "totals": totals,
            "date_du_jour": aujourd_hui,
        },
    )


# ==========================================================
# Détail de la répartition d'un prêt
# ==========================================================

@login_required
def pret_remboursement_detail(request, pk: int):
    """
    Affiche le détail du remboursement d'un prêt approuvé
    et sa répartition entre les membres actifs du groupe.
    """

    demande = get_object_or_404(
        PretDemande.objects.select_related(
            "member",
            "member__group",
            "member__group__admin",
            "member__user",
        ),
        pk=pk,
    )

    group = demande.member.group

    # ======================================================
    # Permissions
    # ======================================================

    has_permission = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_permission:
        messages.error(
            request,
            "Seul l'administrateur du groupe peut consulter cette page.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    if demande.statut not in ["APPROVED", "CLOSED"]:
        messages.info(
            request,
            "Cette demande n'est pas approuvée.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Membres actifs
    # ======================================================

    membres_qs = (
        GroupMember.objects
        .filter(
            group=group,
            actif=True,
        )
        .select_related("user")
        .order_by("id")
    )

    nb_membres = membres_qs.count() or 1

    # ======================================================
    # Totaux du prêt
    # ======================================================

    total = Decimal(
        str(demande.total_a_rembourser or 0)
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    mensualite = Decimal(
        str(demande.mensualite or 0)
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    # ======================================================
    # Part théorique par membre
    # ======================================================

    part_totale = (
        total / Decimal(nb_membres)
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    part_mensuelle = (
        mensualite / Decimal(nb_membres)
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    ) if demande.nb_mois else part_totale

    # Les remboursements sont rattachés au prêt et non à un
    # membre payeur distinct dans le modèle actuel.
    total_rembourse = (
        PretRemboursement.objects
        .filter(
            pret=demande,
            statut="VALIDE",
        )
        .aggregate(total=Sum("montant"))
        .get("total")
        or Decimal("0")
    )

    total_rembourse = Decimal(
        str(total_rembourse)
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    repartition = []

    for membre in membres_qs:
        # Répartition indicative égale entre les membres.
        verse = min(
            total_rembourse / Decimal(nb_membres),
            part_totale,
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

        reste = max(
            part_totale - verse,
            Decimal("0"),
        )

        repartition.append(
            {
                "member": membre,
                "part_totale": part_totale,
                "part_mensuelle": part_mensuelle,
                "verse": verse,
                "reste": reste,
            }
        )

    context = {
        "group": group,
        "demande": demande,
        "repartition": repartition,
        "total": total,
        "mensualite": mensualite,
        "nb_membres": nb_membres,
        "total_rembourse": total_rembourse,
    }

    return render(
        request,
        "epargnecredit/pret_remboursement_detail.html",
        context,
    )


# ==========================================================
# Enregistrement manuel d'un remboursement
# ==========================================================

@login_required
@transaction.atomic
def initier_paiement_remboursement(
    request,
    member_id: int,
):
    """
    Enregistre manuellement un remboursement de prêt.

    ``member_id`` correspond au membre du groupe de
    remboursement. Le prêt est recherché dans le groupe
    d'épargne parent pour le même utilisateur.
    """

    # ======================================================
    # Membre du groupe de remboursement
    # ======================================================

    member = get_object_or_404(
        GroupMember.objects.select_related(
            "group",
            "group__admin",
            "group__parent_group",
            "group__parent_group__admin",
            "user",
        ),
        id=member_id,
        actif=True,
    )

    remboursement_group = member.group
    parent_group = remboursement_group.parent_group

    # ======================================================
    # Vérification du groupe de remboursement
    # ======================================================

    if not remboursement_group.is_remboursement:
        messages.error(
            request,
            (
                "Ce membre n'appartient pas à un groupe "
                "de remboursement."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=remboursement_group.id,
        )

    if parent_group is None:
        messages.error(
            request,
            "Le groupe d'épargne associé est introuvable.",
        )
        return redirect("epargnecredit:group_list")

    # ======================================================
    # Vérification des autorisations
    # ======================================================

    has_access = (
        request.user == member.user
        or request.user == remboursement_group.admin
        or request.user == parent_group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_access:
        messages.error(
            request,
            (
                "Vous n'avez pas l'autorisation "
                "d'enregistrer ce remboursement."
            ),
        )
        return redirect(
            "epargnecredit:group_detail_remboursement",
            group_id=remboursement_group.id,
        )

    # ======================================================
    # Recherche et verrouillage du prêt actif
    # ======================================================

    pret = (
        PretDemande.objects
        .select_for_update()
        .select_related(
            "member",
            "member__user",
            "member__group",
        )
        .filter(
            member__user_id=member.user_id,
            member__group_id=parent_group.id,
            statut="APPROVED",
        )
        .order_by("-created_at")
        .first()
    )

    if pret is None:
        messages.error(
            request,
            f"Aucun prêt actif trouvé pour {member.user}.",
        )
        return redirect(
            "epargnecredit:group_detail_remboursement",
            group_id=remboursement_group.id,
        )

    # ======================================================
    # Montants du prêt
    # ======================================================

    total_a_rembourser = Decimal(
        str(pret.total_a_rembourser or 0)
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    mensualite = Decimal(
        str(pret.mensualite or 0)
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    total_rembourse = (
        PretRemboursement.objects
        .filter(
            pret=pret,
            statut="VALIDE",
        )
        .aggregate(total=Sum("montant"))
        .get("total")
        or Decimal("0")
    )

    total_rembourse = Decimal(
        str(total_rembourse)
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    reste = max(
        total_a_rembourser - total_rembourse,
        Decimal("0"),
    )

    mensualite_proposee = min(
        mensualite,
        reste,
    )

    # ======================================================
    # Prêt déjà soldé
    # ======================================================

    if reste <= 0:
        pret.statut = "CLOSED"
        pret.save(update_fields=["statut"])

        messages.info(
            request,
            "Ce prêt est déjà entièrement remboursé.",
        )
        return redirect(
            "epargnecredit:group_detail_remboursement",
            group_id=remboursement_group.id,
        )

    # ======================================================
    # Traitement du formulaire
    # ======================================================

    if request.method == "POST":
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

            if montant != montant.to_integral_value():
                messages.error(
                    request,
                    "Le montant doit être un nombre entier en FCFA.",
                )

            elif montant <= 0:
                messages.error(
                    request,
                    "Le montant doit être supérieur à zéro.",
                )

            elif montant > reste:
                messages.error(
                    request,
                    (
                        "Le montant saisi dépasse le reste à payer : "
                        f"{reste:,.0f} FCFA."
                    ),
                )

            else:
                montant = montant.quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )

                remboursement = PretRemboursement.objects.create(
                    pret=pret,
                    montant=montant,
                    methode="MANUEL",
                    statut="VALIDE",
                    valide_par=request.user,
                )

                nouveau_total_rembourse = (
                    total_rembourse
                    + remboursement.montant
                )

                nouveau_reste = max(
                    total_a_rembourser
                    - nouveau_total_rembourse,
                    Decimal("0"),
                )

                if nouveau_reste <= 0:
                    pret.statut = "CLOSED"
                    pret.save(update_fields=["statut"])

                    messages.success(
                        request,
                        (
                            f"Remboursement de {montant:,.0f} FCFA "
                            "enregistré avec succès. "
                            "Le prêt est maintenant entièrement soldé."
                        ),
                    )
                else:
                    messages.success(
                        request,
                        (
                            f"Remboursement de {montant:,.0f} FCFA "
                            "enregistré avec succès. "
                            f"Reste à payer : "
                            f"{nouveau_reste:,.0f} FCFA."
                        ),
                    )

                return redirect(
                    "epargnecredit:group_detail_remboursement",
                    group_id=remboursement_group.id,
                )

        except (InvalidOperation, ValueError, TypeError):
            messages.error(
                request,
                "Veuillez saisir un montant valide.",
            )

    # ======================================================
    # Informations indicatives sur les frais
    # ======================================================

    taux_frais_plateforme = Decimal("1.00")

    # ======================================================
    # Affichage du formulaire
    # ======================================================

    context = {
        "member": member,
        "group": remboursement_group,
        "parent_group": parent_group,
        "pret": pret,
        "total_a_rembourser": total_a_rembourser,
        "total_rembourse": total_rembourse,
        "reste": reste,
        "mensualite": mensualite_proposee,
        "taux_frais_plateforme": taux_frais_plateforme,
    }

    return render(
        request,
        "epargnecredit/initier_paiement_remboursement.html",
        context,
    )
