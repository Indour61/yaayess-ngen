import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from epargnecredit.models import GroupMember, Versement
from epargnecredit.utils_notification import notifier_validation_versement
from epargnecredit.utils_pdf import generer_recu_pdf


logger = logging.getLogger(__name__)

TAUX_FRAIS_PLATEFORME = Decimal("1.00")
PAYDUNYA_TIMEOUT = 30


# ==========================================================
# Fonctions utilitaires
# ==========================================================

def _arrondir_fcfa(valeur) -> Decimal:
    return Decimal(str(valeur or 0)).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


def _configuration_paydunya():
    """
    Retourne les paramètres PayDunya définis dans settings.py.
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


def _extraire_montant(request) -> Decimal:
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

    if montant <= 0:
        raise ValueError(
            "Le montant doit être supérieur à zéro."
        )

    if montant != montant.to_integral_value():
        raise ValueError(
            "Le montant doit être un nombre entier en FCFA."
        )

    return montant.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


def _calculer_frais(montant: Decimal) -> Decimal:
    return (
        montant
        * TAUX_FRAIS_PLATEFORME
        / Decimal("100")
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


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


def _executer_actions_apres_validation(versement):
    """
    Génère le reçu et notifie le membre.

    Les erreurs annexes ne doivent pas annuler la validation
    financière du versement.
    """

    try:
        generer_recu_pdf(versement)
    except Exception:
        logger.exception(
            "Erreur de génération du reçu du versement %s",
            versement.pk,
        )

    try:
        notifier_validation_versement(
            versement.member.user,
            versement.montant,
        )
    except Exception:
        logger.exception(
            "Erreur de notification du versement %s",
            versement.pk,
        )


def _mettre_a_jour_depuis_paydunya(
    versement,
    donnees,
):
    """
    Met à jour un versement après vérification PayDunya.

    Le traitement est idempotent : un versement déjà validé
    n'est pas comptabilisé ou notifié une seconde fois.
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
        versement.montant_total
    )

    versement.paydunya_status = (
        statut_paydunya.upper()
        if statut_paydunya
        else versement.paydunya_status
    )
    versement.paydunya_response = donnees

    transaction_id = (
        donnees.get("transaction_id")
        or facture.get("transaction_id")
    )

    if transaction_id:
        versement.transaction_id = str(
            transaction_id
        )

    champs = [
        "paydunya_status",
        "paydunya_response",
        "transaction_id",
    ]

    if statut_paydunya == "completed":
        if montant_recu != montant_attendu:
            if versement.statut != "VALIDE":
                versement.statut = "ECHEC"
                champs.append("statut")

            versement.save(
                update_fields=list(dict.fromkeys(champs))
            )

            logger.error(
                "Montant PayDunya incorrect pour versement %s : "
                "attendu=%s reçu=%s",
                versement.pk,
                montant_attendu,
                montant_recu,
            )
            return "montant_incorrect", False

        nouvellement_valide = (
            versement.statut != "VALIDE"
        )

        if nouvellement_valide:
            maintenant = timezone.now()
            versement.statut = "VALIDE"
            versement.date_validation = maintenant
            versement.date_paiement = maintenant

            champs.extend(
                [
                    "statut",
                    "date_validation",
                    "date_paiement",
                ]
            )

        versement.save(
            update_fields=list(dict.fromkeys(champs))
        )

        return "valide", nouvellement_valide

    if statut_paydunya in {"cancelled", "canceled"}:
        if versement.statut != "VALIDE":
            versement.statut = "ANNULE"
            champs.append("statut")

        versement.save(
            update_fields=list(dict.fromkeys(champs))
        )
        return "annule", False

    if statut_paydunya == "failed":
        if versement.statut != "VALIDE":
            versement.statut = "ECHEC"
            champs.append("statut")

        versement.save(
            update_fields=list(dict.fromkeys(champs))
        )
        return "echec", False

    versement.save(
        update_fields=list(dict.fromkeys(champs))
    )
    return "en_attente", False


# ==========================================================
# Déclaration d'un versement en caisse ou via PayDunya
# ==========================================================

@login_required
def initier_versement(request, member_id):
    """
    Enregistre un versement en caisse ou initie un paiement PayDunya.

    Pour la caisse, le versement reste EN_ATTENTE jusqu'à sa
    validation par l'administrateur.

    Pour PayDunya, le versement est automatiquement validé après
    confirmation serveur-à-serveur du paiement.
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

    if request.method == "GET":
        return render(
            request,
            "epargnecredit/initier_versement.html",
            {
                "member": member,
                "group": group,
                "taux_frais_plateforme": (
                    TAUX_FRAIS_PLATEFORME
                ),
            },
        )

    methode = str(
        request.POST.get("methode", "CAISSE")
    ).strip().upper()

    if methode not in {"CAISSE", "MANUEL", "PAYDUNYA"}:
        messages.error(
            request,
            "Méthode de paiement invalide.",
        )
        return redirect(
            "epargnecredit:initier_versement",
            member_id=member.id,
        )

    try:
        montant = _extraire_montant(request)
    except InvalidOperation:
        messages.error(
            request,
            "Veuillez saisir un montant valide.",
        )
        return redirect(
            "epargnecredit:initier_versement",
            member_id=member.id,
        )
    except (ValueError, TypeError) as exc:
        messages.error(
            request,
            str(exc),
        )
        return redirect(
            "epargnecredit:initier_versement",
            member_id=member.id,
        )

    frais = _calculer_frais(montant)

    if methode in {"CAISSE", "MANUEL"}:
        with transaction.atomic():
            versement = Versement.objects.create(
                member=member,
                montant=montant,
                frais=frais,
                methode=methode,
                statut="EN_ATTENTE",
            )

        messages.success(
            request,
            (
                f"Versement de {versement.montant:,.0f} FCFA "
                "enregistré. "
                f"Frais plateforme : "
                f"{versement.frais:,.0f} FCFA. "
                "Le versement est en attente de validation."
            ),
        )

        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    with transaction.atomic():
        versement = Versement.objects.create(
            member=member,
            montant=montant,
            frais=frais,
            methode="PAYDUNYA",
            statut="EN_ATTENTE",
        )

    try:
        configuration = _configuration_paydunya()

        return_url = request.build_absolute_uri(
            reverse(
                "epargnecredit:paydunya_versement_return"
            )
        )

        cancel_url = request.build_absolute_uri(
            reverse(
                "epargnecredit:paydunya_versement_cancel"
            )
        )

        callback_url = request.build_absolute_uri(
            reverse(
                "epargnecredit:paydunya_versement_ipn"
            )
        )

        utilisateur = member.user

        payload = {
            "invoice": {
                "items": {
                    "versement": {
                        "name": "Versement épargne YAAYESS",
                        "quantity": 1,
                        "unit_price": int(montant),
                        "total_price": int(montant),
                        "description": (
                            f"Versement dans le groupe "
                            f"{group.nom}"
                        ),
                    },
                },
                "taxes": {
                    "frais_yaayess": {
                        "name": (
                            "Frais plateforme YAAYESS (1 %)"
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
                    versement.montant_total
                ),
                "description": (
                    f"Versement épargne YAAYESS "
                    f"- groupe {group.nom}"
                ),
            },
            "store": {
                "name": configuration["store_name"],
            },
            "custom_data": {
                "type": "versement_epargnecredit",
                "versement_id": versement.pk,
                "member_id": member.pk,
                "group_id": group.pk,
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

        versement.paydunya_response = donnees

        if (
            reponse.status_code < 400
            and donnees.get("response_code") == "00"
            and donnees.get("token")
            and donnees.get("response_text")
        ):
            versement.paydunya_token = str(
                donnees["token"]
            )
            versement.paydunya_invoice_url = str(
                donnees["response_text"]
            )
            versement.paydunya_status = "PENDING"

            versement.save(
                update_fields=[
                    "paydunya_token",
                    "paydunya_invoice_url",
                    "paydunya_status",
                    "paydunya_response",
                ]
            )

            return redirect(
                versement.paydunya_invoice_url
            )

        versement.statut = "ECHEC"
        versement.paydunya_status = "FAILED"

        versement.save(
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
        versement.statut = "ECHEC"
        versement.paydunya_status = "FAILED"
        versement.paydunya_response = {
            "error": str(exc),
        }

        versement.save(
            update_fields=[
                "statut",
                "paydunya_status",
                "paydunya_response",
            ]
        )

        logger.exception(
            "Échec de création PayDunya pour le versement %s",
            versement.pk,
        )

        messages.error(
            request,
            (
                "Impossible de contacter PayDunya. "
                "Veuillez réessayer."
            ),
        )

    return redirect(
        "epargnecredit:initier_versement",
        member_id=member.id,
    )


# ==========================================================
# Retour utilisateur PayDunya
# ==========================================================

@login_required
@require_GET
def paydunya_versement_return(request):
    token = str(
        request.GET.get("token", "")
    ).strip()

    if not token:
        messages.error(
            request,
            "Token PayDunya absent.",
        )
        return redirect("epargnecredit:group_list")

    versement = get_object_or_404(
        Versement.objects.select_related(
            "member",
            "member__group",
            "member__group__admin",
            "member__user",
        ),
        paydunya_token=token,
        methode="PAYDUNYA",
    )

    group = versement.member.group

    has_access = (
        request.user == versement.member.user
        or request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_access:
        messages.error(
            request,
            "Accès non autorisé à ce paiement.",
        )
        return redirect("epargnecredit:group_list")

    nouvellement_valide = False

    try:
        donnees = _verifier_paiement_paydunya(token)

        with transaction.atomic():
            versement = (
                Versement.objects
                .select_for_update()
                .select_related(
                    "member",
                    "member__user",
                    "member__group",
                )
                .get(pk=versement.pk)
            )

            resultat, nouvellement_valide = (
                _mettre_a_jour_depuis_paydunya(
                    versement,
                    donnees,
                )
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
        if nouvellement_valide:
            _executer_actions_apres_validation(
                versement
            )

        if resultat == "valide":
            messages.success(
                request,
                (
                    f"Paiement confirmé. Versement de "
                    f"{versement.montant:,.0f} FCFA validé."
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

    return redirect(
        "epargnecredit:group_detail",
        group_id=group.id,
    )


# ==========================================================
# Annulation utilisateur PayDunya
# ==========================================================

@login_required
@require_GET
def paydunya_versement_cancel(request):
    token = str(
        request.GET.get("token", "")
    ).strip()

    if token:
        versement = (
            Versement.objects
            .filter(
                paydunya_token=token,
                methode="PAYDUNYA",
            )
            .select_related(
                "member",
                "member__group",
            )
            .first()
        )

        if versement is not None:
            group = versement.member.group

            has_access = (
                request.user == versement.member.user
                or request.user == group.admin
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

            if versement.statut != "VALIDE":
                versement.statut = "ANNULE"
                versement.paydunya_status = "CANCELLED"
                versement.save(
                    update_fields=[
                        "statut",
                        "paydunya_status",
                    ]
                )

            messages.warning(
                request,
                "Le paiement PayDunya a été annulé.",
            )

            return redirect(
                "epargnecredit:group_detail",
                group_id=group.id,
            )

    messages.warning(
        request,
        "Le paiement PayDunya a été annulé.",
    )

    return redirect("epargnecredit:group_list")


# ==========================================================
# IPN / callback PayDunya
# ==========================================================

@csrf_exempt
@require_POST
def paydunya_versement_ipn(request):
    """
    Reçoit la notification PayDunya dans le champ ``data``.
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
        or not hashlib.compare_digest(
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
    ).strip()

    if not token:
        return JsonResponse(
            {
                "status": "error",
                "message": "Token absent.",
            },
            status=400,
        )

    versement = (
        Versement.objects
        .filter(
            paydunya_token=token,
            methode="PAYDUNYA",
        )
        .select_related(
            "member",
            "member__user",
            "member__group",
        )
        .first()
    )

    if versement is None:
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
        donnees_verifiees = _verifier_paiement_paydunya(
            token
        )

        with transaction.atomic():
            versement = (
                Versement.objects
                .select_for_update()
                .select_related(
                    "member",
                    "member__user",
                    "member__group",
                )
                .get(pk=versement.pk)
            )

            resultat, nouvellement_valide = (
                _mettre_a_jour_depuis_paydunya(
                    versement,
                    donnees_verifiees,
                )
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

    if nouvellement_valide:
        _executer_actions_apres_validation(
            versement
        )

    return JsonResponse(
        {
            "status": "ok",
            "result": resultat,
        }
    )


# ==========================================================
# Validation manuelle d'un versement
# ==========================================================

@login_required
@require_POST
@transaction.atomic
def valider_versement(request, versement_id):
    """
    Valide un versement manuel en attente.

    Un versement PayDunya ne doit pas être validé manuellement.
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

    if versement.methode == "PAYDUNYA":
        messages.error(
            request,
            (
                "Un versement PayDunya doit être validé "
                "uniquement après confirmation PayDunya."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    if versement.statut != "EN_ATTENTE":
        messages.warning(
            request,
            "Ce versement a déjà été traité.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    versement.valider(request.user)

    transaction.on_commit(
        lambda: _executer_actions_apres_validation(
            versement
        )
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
    Refuse un versement manuel en attente.

    Un paiement PayDunya doit être annulé ou échouer côté
    PayDunya et ne doit pas être refusé manuellement.
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

    if versement.methode == "PAYDUNYA":
        messages.error(
            request,
            (
                "Un versement PayDunya ne peut pas être "
                "refusé manuellement."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    if versement.statut != "EN_ATTENTE":
        messages.warning(
            request,
            "Ce versement a déjà été traité.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

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
