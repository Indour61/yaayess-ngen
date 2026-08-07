import calendar
import hashlib
import hmac
import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

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
# Paiement d'un remboursement : Caisse ou PayDunya
# ==========================================================

logger = logging.getLogger(__name__)

TAUX_FRAIS_PLATEFORME = Decimal("1.00")
PAYDUNYA_TIMEOUT = 30


def _arrondir_fcfa(valeur) -> Decimal:
    return Decimal(str(valeur or 0)).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


def _configuration_paydunya():
    """
    Retourne la configuration PayDunya définie dans settings.py.
    """

    mode = str(
        getattr(settings, "PAYDUNYA_MODE", "test")
    ).strip().lower()

    if mode not in {"test", "live", "production"}:
        mode = "test"

    est_test = mode == "test"

    configuration = {
        "mode": "test" if est_test else "live",
        "base_url": (
            "https://app.paydunya.com/sandbox-api/v1"
            if est_test
            else "https://app.paydunya.com/api/v1"
        ),
        "master_key": getattr(
            settings,
            "PAYDUNYA_MASTER_KEY",
            "",
        ),
        "private_key": getattr(
            settings,
            "PAYDUNYA_PRIVATE_KEY",
            "",
        ),
        "token": getattr(
            settings,
            "PAYDUNYA_TOKEN",
            "",
        ),
        "store_name": getattr(
            settings,
            "PAYDUNYA_STORE_NAME",
            "YAAYESS",
        ),
    }

    champs_manquants = [
        nom
        for nom in (
            "master_key",
            "private_key",
            "token",
        )
        if not configuration[nom]
    ]

    if champs_manquants:
        raise ValueError(
            "Configuration PayDunya incomplète : "
            + ", ".join(champs_manquants)
        )

    return configuration


def _entetes_paydunya(configuration):
    return {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": configuration["master_key"],
        "PAYDUNYA-PRIVATE-KEY": configuration["private_key"],
        "PAYDUNYA-TOKEN": configuration["token"],
    }


def _nom_utilisateur(utilisateur) -> str:
    nom_complet = ""

    get_full_name = getattr(
        utilisateur,
        "get_full_name",
        None,
    )

    if callable(get_full_name):
        nom_complet = get_full_name()

    return str(
        getattr(utilisateur, "nom", "")
        or nom_complet
        or getattr(utilisateur, "phone", "")
        or utilisateur
    ).strip()


def _email_utilisateur(utilisateur) -> str:
    return str(
        getattr(utilisateur, "email", "")
        or ""
    ).strip()


def _telephone_utilisateur(utilisateur) -> str:
    return str(
        getattr(utilisateur, "phone", "")
        or getattr(utilisateur, "telephone", "")
        or ""
    ).strip()


def _calculer_situation_pret(pret):
    total_a_rembourser = _arrondir_fcfa(
        pret.total_a_rembourser
    )

    mensualite = _arrondir_fcfa(
        pret.mensualite
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

    total_rembourse = _arrondir_fcfa(
        total_rembourse
    )

    reste = max(
        total_a_rembourser - total_rembourse,
        Decimal("0"),
    )

    mensualite_proposee = min(
        mensualite,
        reste,
    )

    return {
        "total_a_rembourser": total_a_rembourser,
        "mensualite": mensualite,
        "total_rembourse": total_rembourse,
        "reste": reste,
        "mensualite_proposee": mensualite_proposee,
    }


def _extraire_montant(request, reste):
    montant_brut = request.POST.get("montant", "")

    montant_str = (
        str(montant_brut)
        .strip()
        .replace("\u00a0", "")
        .replace(" ", "")
        .replace(",", ".")
    )

    if not montant_str:
        raise InvalidOperation

    montant = Decimal(montant_str)

    if montant != montant.to_integral_value():
        raise ValueError(
            "Le montant doit être un nombre entier en FCFA."
        )

    if montant <= 0:
        raise ValueError(
            "Le montant doit être supérieur à zéro."
        )

    if montant > reste:
        raise ValueError(
            "Le montant saisi dépasse le reste à payer : "
            f"{reste:,.0f} FCFA."
        )

    return montant.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


def _fermer_pret_si_solde(pret):
    total_valide = (
        PretRemboursement.objects
        .filter(
            pret=pret,
            statut="VALIDE",
        )
        .aggregate(total=Sum("montant"))
        .get("total")
        or Decimal("0")
    )

    reste = max(
        _arrondir_fcfa(pret.total_a_rembourser)
        - _arrondir_fcfa(total_valide),
        Decimal("0"),
    )

    if reste <= 0 and pret.statut != "CLOSED":
        pret.statut = "CLOSED"
        pret.save(update_fields=["statut"])

    return reste


def _verifier_paiement_paydunya(token):
    configuration = _configuration_paydunya()

    url = (
        f"{configuration['base_url']}"
        f"/checkout-invoice/confirm/{token}"
    )

    reponse = requests.get(
        url,
        headers=_entetes_paydunya(configuration),
        timeout=PAYDUNYA_TIMEOUT,
    )

    try:
        donnees = reponse.json()
    except ValueError as exc:
        raise RuntimeError(
            "Réponse PayDunya invalide."
        ) from exc

    if reponse.status_code >= 400:
        raise RuntimeError(
            donnees.get("response_text")
            or f"Erreur HTTP PayDunya {reponse.status_code}."
        )

    return donnees


def _mettre_a_jour_depuis_paydunya(
    remboursement,
    donnees,
):
    """
    Met à jour un remboursement après confirmation PayDunya.

    Le traitement est idempotent : une transaction déjà validée
    n'est jamais comptabilisée une seconde fois.
    """

    facture = donnees.get("invoice") or {}

    statut_paydunya = str(
        donnees.get("status")
        or facture.get("status")
        or ""
    ).strip().lower()

    montant_recu = _arrondir_fcfa(
        facture.get("total_amount", 0)
    )

    montant_attendu = _arrondir_fcfa(
        remboursement.montant_total
    )

    remboursement.paydunya_status = (
        statut_paydunya.upper()
        if statut_paydunya
        else remboursement.paydunya_status
    )

    remboursement.paydunya_response = donnees

    transaction_id = (
        donnees.get("transaction_id")
        or facture.get("transaction_id")
    )

    if transaction_id:
        remboursement.transaction_id = str(
            transaction_id
        )

    champs = [
        "paydunya_status",
        "paydunya_response",
        "transaction_id",
    ]

    if statut_paydunya == "completed":
        if montant_recu != montant_attendu:
            if remboursement.statut != "VALIDE":
                remboursement.statut = "ECHEC"
                champs.append("statut")

            remboursement.save(
                update_fields=list(dict.fromkeys(champs))
            )

            logger.error(
                "Montant PayDunya incorrect pour remboursement %s : "
                "attendu=%s reçu=%s",
                remboursement.pk,
                montant_attendu,
                montant_recu,
            )

            return "montant_incorrect"

        if remboursement.statut != "VALIDE":
            maintenant = timezone.now()

            remboursement.statut = "VALIDE"
            remboursement.date_validation = maintenant
            remboursement.date_paiement = maintenant

            champs.extend(
                [
                    "statut",
                    "date_validation",
                    "date_paiement",
                ]
            )

        remboursement.save(
            update_fields=list(dict.fromkeys(champs))
        )

        _fermer_pret_si_solde(
            remboursement.pret
        )

        return "valide"

    if statut_paydunya in {"cancelled", "canceled"}:
        if remboursement.statut != "VALIDE":
            remboursement.statut = "ANNULE"
            champs.append("statut")

        remboursement.save(
            update_fields=list(dict.fromkeys(champs))
        )

        return "annule"

    if statut_paydunya == "failed":
        if remboursement.statut != "VALIDE":
            remboursement.statut = "ECHEC"
            champs.append("statut")

        remboursement.save(
            update_fields=list(dict.fromkeys(champs))
        )

        return "echec"

    remboursement.save(
        update_fields=list(dict.fromkeys(champs))
    )

    return "en_attente"


@login_required
def initier_paiement_remboursement(
    request,
    member_id: int,
):
    """
    Enregistre un remboursement en caisse ou initie PayDunya.

    ``member_id`` désigne le membre du groupe de remboursement.
    Le prêt actif est recherché dans le groupe d'épargne parent
    pour le même utilisateur.
    """

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

        return redirect(
            "epargnecredit:group_list"
        )

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

    pret = (
        PretDemande.objects
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

    situation = _calculer_situation_pret(pret)

    total_a_rembourser = situation[
        "total_a_rembourser"
    ]
    mensualite = situation["mensualite"]
    total_rembourse = situation["total_rembourse"]
    reste = situation["reste"]
    mensualite_proposee = situation[
        "mensualite_proposee"
    ]

    if reste <= 0:
        if pret.statut != "CLOSED":
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

    if request.method == "POST":
        methode = str(
            request.POST.get("methode", "CAISSE")
        ).strip().upper()

        if methode not in {"CAISSE", "MANUEL", "PAYDUNYA"}:
            messages.error(
                request,
                "Méthode de paiement invalide.",
            )
        else:
            try:
                montant = _extraire_montant(
                    request,
                    reste,
                )

            except InvalidOperation:
                messages.error(
                    request,
                    "Veuillez saisir un montant valide.",
                )

            except (ValueError, TypeError) as exc:
                messages.error(
                    request,
                    str(exc),
                )

            else:
                if methode in {"CAISSE", "MANUEL"}:
                    with transaction.atomic():
                        pret_verrouille = (
                            PretDemande.objects
                            .select_for_update()
                            .get(pk=pret.pk)
                        )

                        situation_verrouillee = (
                            _calculer_situation_pret(
                                pret_verrouille
                            )
                        )

                        reste_verrouille = (
                            situation_verrouillee["reste"]
                        )

                        if montant > reste_verrouille:
                            messages.error(
                                request,
                                (
                                    "Le reste à payer a changé. "
                                    f"Nouveau reste : "
                                    f"{reste_verrouille:,.0f} FCFA."
                                ),
                            )

                            return redirect(
                                "epargnecredit:"
                                "initier_paiement_remboursement",
                                member_id=member.id,
                            )

                        remboursement = (
                            PretRemboursement.objects.create(
                                pret=pret_verrouille,
                                montant=montant,
                                frais=Decimal("0"),
                                methode=methode,
                                statut="VALIDE",
                                valide_par=request.user,
                                date_validation=timezone.now(),
                                date_paiement=timezone.now(),
                            )
                        )

                        nouveau_reste = (
                            _fermer_pret_si_solde(
                                pret_verrouille
                            )
                        )

                    if nouveau_reste <= 0:
                        messages.success(
                            request,
                            (
                                f"Remboursement de "
                                f"{remboursement.montant:,.0f} FCFA "
                                "enregistré. Le prêt est soldé."
                            ),
                        )
                    else:
                        messages.success(
                            request,
                            (
                                f"Remboursement de "
                                f"{remboursement.montant:,.0f} FCFA "
                                "enregistré avec succès. "
                                f"Reste à payer : "
                                f"{nouveau_reste:,.0f} FCFA."
                            ),
                        )

                    return redirect(
                        "epargnecredit:"
                        "group_detail_remboursement",
                        group_id=remboursement_group.id,
                    )

                frais = (
                    montant
                    * TAUX_FRAIS_PLATEFORME
                    / Decimal("100")
                ).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )

                with transaction.atomic():
                    pret_verrouille = (
                        PretDemande.objects
                        .select_for_update()
                        .get(pk=pret.pk)
                    )

                    situation_verrouillee = (
                        _calculer_situation_pret(
                            pret_verrouille
                        )
                    )

                    reste_verrouille = (
                        situation_verrouillee["reste"]
                    )

                    if montant > reste_verrouille:
                        messages.error(
                            request,
                            (
                                "Le reste à payer a changé. "
                                f"Nouveau reste : "
                                f"{reste_verrouille:,.0f} FCFA."
                            ),
                        )

                        return redirect(
                            "epargnecredit:"
                            "initier_paiement_remboursement",
                            member_id=member.id,
                        )

                    remboursement = (
                        PretRemboursement.objects.create(
                            pret=pret_verrouille,
                            montant=montant,
                            frais=frais,
                            methode="PAYDUNYA",
                            statut="EN_ATTENTE",
                        )
                    )

                try:
                    configuration = _configuration_paydunya()

                    return_url = request.build_absolute_uri(
                        reverse(
                            "epargnecredit:"
                            "paydunya_remboursement_return"
                        )
                    )

                    cancel_url = request.build_absolute_uri(
                        reverse(
                            "epargnecredit:"
                            "paydunya_remboursement_cancel"
                        )
                    )

                    callback_url = request.build_absolute_uri(
                        reverse(
                            "epargnecredit:"
                            "paydunya_remboursement_ipn"
                        )
                    )

                    utilisateur = member.user

                    payload = {
                        "invoice": {
                            "items": {
                                "remboursement": {
                                    "name": (
                                        "Remboursement de crédit YAAYESS"
                                    ),
                                    "quantity": 1,
                                    "unit_price": int(montant),
                                    "total_price": int(montant),
                                    "description": (
                                        f"Remboursement du prêt "
                                        f"#{pret.pk}"
                                    ),
                                },
                            },
                            "taxes": {
                                "frais_yaayess": {
                                    "name": (
                                        "Frais plateforme YAAYESS "
                                        "(1 %)"
                                    ),
                                    "amount": int(frais),
                                },
                            },
                            "customer": {
                                "name": _nom_utilisateur(
                                    utilisateur
                                ),
                                "email": _email_utilisateur(
                                    utilisateur
                                ),
                                "phone": _telephone_utilisateur(
                                    utilisateur
                                ),
                            },
                            "total_amount": int(
                                remboursement.montant_total
                            ),
                            "description": (
                                f"Remboursement du crédit "
                                f"YAAYESS #{pret.pk}"
                            ),
                        },
                        "store": {
                            "name": configuration["store_name"],
                        },
                        "custom_data": {
                            "type": "remboursement_pret",
                            "remboursement_id": remboursement.pk,
                            "pret_id": pret.pk,
                            "member_id": member.pk,
                            "montant": str(montant),
                            "frais": str(frais),
                        },
                        "actions": {
                            "cancel_url": cancel_url,
                            "return_url": return_url,
                            "callback_url": callback_url,
                        },
                    }

                    reponse = requests.post(
                        (
                            f"{configuration['base_url']}"
                            "/checkout-invoice/create"
                        ),
                        json=payload,
                        headers=_entetes_paydunya(
                            configuration
                        ),
                        timeout=PAYDUNYA_TIMEOUT,
                    )

                    try:
                        donnees = reponse.json()
                    except ValueError as exc:
                        raise RuntimeError(
                            "Réponse PayDunya invalide."
                        ) from exc

                    remboursement.paydunya_response = donnees

                    if (
                        reponse.status_code < 400
                        and donnees.get("response_code") == "00"
                        and donnees.get("token")
                        and donnees.get("response_text")
                    ):
                        remboursement.paydunya_token = str(
                            donnees["token"]
                        )
                        remboursement.paydunya_invoice_url = str(
                            donnees["response_text"]
                        )
                        remboursement.paydunya_status = "PENDING"

                        remboursement.save(
                            update_fields=[
                                "paydunya_token",
                                "paydunya_invoice_url",
                                "paydunya_status",
                                "paydunya_response",
                            ]
                        )

                        return redirect(
                            remboursement.paydunya_invoice_url
                        )

                    remboursement.statut = "ECHEC"
                    remboursement.paydunya_status = "FAILED"

                    remboursement.save(
                        update_fields=[
                            "statut",
                            "paydunya_status",
                            "paydunya_response",
                        ]
                    )

                    messages.error(
                        request,
                        (
                            "PayDunya n'a pas pu créer la facture : "
                            f"{donnees.get('response_text', 'erreur inconnue')}"
                        ),
                    )

                except (
                    requests.RequestException,
                    RuntimeError,
                    ValueError,
                ) as exc:
                    remboursement.statut = "ECHEC"
                    remboursement.paydunya_status = "FAILED"
                    remboursement.paydunya_response = {
                        "error": str(exc),
                    }

                    remboursement.save(
                        update_fields=[
                            "statut",
                            "paydunya_status",
                            "paydunya_response",
                        ]
                    )

                    logger.exception(
                        "Échec de création PayDunya pour "
                        "le remboursement %s",
                        remboursement.pk,
                    )

                    messages.error(
                        request,
                        (
                            "Impossible de contacter PayDunya. "
                            "Veuillez réessayer."
                        ),
                    )

    context = {
        "member": member,
        "group": remboursement_group,
        "parent_group": parent_group,
        "pret": pret,
        "total_a_rembourser": total_a_rembourser,
        "total_rembourse": total_rembourse,
        "reste": reste,
        "mensualite": mensualite_proposee,
        "taux_frais_plateforme": TAUX_FRAIS_PLATEFORME,
    }

    return render(
        request,
        "epargnecredit/initier_paiement_remboursement.html",
        context,
    )


# ==========================================================
# Retour utilisateur PayDunya
# ==========================================================

@login_required
@require_GET
def paydunya_remboursement_return(request):
    token = str(
        request.GET.get("token", "")
    ).strip()

    if not token:
        messages.error(
            request,
            "Token PayDunya absent.",
        )

        return redirect(
            "epargnecredit:group_list"
        )

    remboursement = get_object_or_404(
        PretRemboursement.objects.select_related(
            "pret",
            "pret__member",
            "pret__member__group",
            "pret__member__group__admin",
            "pret__member__user",
        ),
        paydunya_token=token,
        methode="PAYDUNYA",
    )

    pret = remboursement.pret
    parent_group = pret.member.group
    remboursement_group = (
        parent_group.get_remboursement_group()
    )

    has_access = (
        request.user == pret.member.user
        or request.user == parent_group.admin
        or (
            remboursement_group is not None
            and request.user == remboursement_group.admin
        )
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_access:
        messages.error(
            request,
            "Accès non autorisé à ce paiement.",
        )

        return redirect(
            "epargnecredit:group_list"
        )

    try:
        donnees = _verifier_paiement_paydunya(
            token
        )

        with transaction.atomic():
            remboursement = (
                PretRemboursement.objects
                .select_for_update()
                .select_related("pret")
                .get(pk=remboursement.pk)
            )

            resultat = _mettre_a_jour_depuis_paydunya(
                remboursement,
                donnees,
            )

    except (
        requests.RequestException,
        RuntimeError,
        ValueError,
    ):
        logger.exception(
            "Erreur de vérification PayDunya pour le token %s",
            token,
        )

        messages.warning(
            request,
            (
                "Le paiement est en cours de vérification. "
                "La confirmation automatique reste active."
            ),
        )

    else:
        if resultat == "valide":
            messages.success(
                request,
                (
                    f"Paiement confirmé. "
                    f"{remboursement.montant:,.0f} FCFA "
                    "ont été affectés au remboursement."
                ),
            )

        elif resultat == "annule":
            messages.warning(
                request,
                "Le paiement PayDunya a été annulé.",
            )

        elif resultat == "echec":
            messages.error(
                request,
                "Le paiement PayDunya a échoué.",
            )

        elif resultat == "montant_incorrect":
            messages.error(
                request,
                (
                    "Le montant confirmé par PayDunya ne "
                    "correspond pas au montant attendu."
                ),
            )

        else:
            messages.info(
                request,
                "Le paiement PayDunya est toujours en attente.",
            )

    if remboursement_group is not None:
        return redirect(
            "epargnecredit:group_detail_remboursement",
            group_id=remboursement_group.id,
        )

    return redirect(
        "epargnecredit:group_list"
    )


# ==========================================================
# Annulation utilisateur PayDunya
# ==========================================================

@login_required
@require_GET
def paydunya_remboursement_cancel(request):
    token = str(
        request.GET.get("token", "")
    ).strip()

    if token:
        remboursement = (
            PretRemboursement.objects
            .filter(
                paydunya_token=token,
                methode="PAYDUNYA",
            )
            .select_related(
                "pret",
                "pret__member",
                "pret__member__group",
                "pret__member__user",
            )
            .first()
        )

        if remboursement is not None:
            pret = remboursement.pret
            parent_group = pret.member.group
            remboursement_group = (
                parent_group.get_remboursement_group()
            )

            has_access = (
                request.user == pret.member.user
                or request.user == parent_group.admin
                or (
                    remboursement_group is not None
                    and request.user == remboursement_group.admin
                )
                or getattr(
                    request.user,
                    "is_super_admin",
                    False,
                )
                or getattr(
                    request.user,
                    "is_superuser",
                    False,
                )
            )

            if not has_access:
                messages.error(
                    request,
                    "Accès non autorisé à ce paiement.",
                )

                return redirect(
                    "epargnecredit:group_list"
                )

            if remboursement.statut != "VALIDE":
                remboursement.statut = "ANNULE"
                remboursement.paydunya_status = "CANCELLED"

                remboursement.save(
                    update_fields=[
                        "statut",
                        "paydunya_status",
                    ]
                )

            messages.warning(
                request,
                "Le paiement PayDunya a été annulé.",
            )

            if remboursement_group is not None:
                return redirect(
                    "epargnecredit:"
                    "group_detail_remboursement",
                    group_id=remboursement_group.id,
                )

    messages.warning(
        request,
        "Le paiement PayDunya a été annulé.",
    )

    return redirect(
        "epargnecredit:group_list"
    )


# ==========================================================
# IPN / callback PayDunya
# ==========================================================

@csrf_exempt
@require_POST
def paydunya_remboursement_ipn(request):
    """
    Reçoit l'IPN PayDunya dans le champ ``data``.
    """

    donnees_brutes = request.POST.get("data")

    if not donnees_brutes:
        return JsonResponse(
            {
                "status": "error",
                "message": "Champ data absent.",
            },
            status=400,
        )

    try:
        donnees = (
            json.loads(donnees_brutes)
            if isinstance(donnees_brutes, str)
            else donnees_brutes
        )

    except (TypeError, json.JSONDecodeError):
        logger.warning(
            "IPN PayDunya invalide : JSON illisible."
        )

        return JsonResponse(
            {
                "status": "error",
                "message": "Données IPN invalides.",
            },
            status=400,
        )

    if not isinstance(donnees, dict):
        return JsonResponse(
            {
                "status": "error",
                "message": "Structure IPN invalide.",
            },
            status=400,
        )

    try:
        configuration = _configuration_paydunya()

    except ValueError:
        logger.exception(
            "Configuration PayDunya indisponible pour l'IPN."
        )

        return JsonResponse(
            {
                "status": "error",
                "message": "Configuration indisponible.",
            },
            status=500,
        )

    hash_recu = str(
        donnees.get("hash", "")
    ).strip().lower()

    hash_attendu = hashlib.sha512(
        configuration["master_key"].encode("utf-8")
    ).hexdigest().lower()

    if (
        not hash_recu
        or not hmac.compare_digest(
            hash_recu,
            hash_attendu,
        )
    ):
        logger.warning(
            "IPN PayDunya rejeté : hash invalide."
        )

        return JsonResponse(
            {
                "status": "error",
                "message": "Signature invalide.",
            },
            status=403,
        )

    facture = donnees.get("invoice") or {}

    token = str(
        facture.get("token", "")
        or donnees.get("token", "")
    ).strip()

    if not token:
        return JsonResponse(
            {
                "status": "error",
                "message": "Token absent.",
            },
            status=400,
        )

    remboursement = (
        PretRemboursement.objects
        .filter(
            paydunya_token=token,
            methode="PAYDUNYA",
        )
        .select_related("pret")
        .first()
    )

    if remboursement is None:
        logger.warning(
            "IPN PayDunya reçu pour token inconnu : %s",
            token,
        )

        return JsonResponse(
            {
                "status": "ignored",
                "message": "Paiement inconnu.",
            },
            status=404,
        )

    try:
        donnees_verifiees = (
            _verifier_paiement_paydunya(token)
        )

        with transaction.atomic():
            remboursement = (
                PretRemboursement.objects
                .select_for_update()
                .select_related("pret")
                .get(pk=remboursement.pk)
            )

            resultat = _mettre_a_jour_depuis_paydunya(
                remboursement,
                donnees_verifiees,
            )

    except (
        requests.RequestException,
        RuntimeError,
        ValueError,
    ):
        logger.exception(
            "Erreur de traitement IPN PayDunya pour %s",
            token,
        )

        return JsonResponse(
            {
                "status": "error",
                "message": "Vérification PayDunya impossible.",
            },
            status=502,
        )

    return JsonResponse(
        {
            "status": "ok",
            "result": resultat,
        }
    )