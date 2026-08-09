import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from cotisationtontine.models import GroupMember, Versement
from cotisationtontine.services.paydunya_service import (
    PayDunyaAPIError,
    PayDunyaConfigurationError,
    create_checkout_invoice,
)


logger = logging.getLogger(__name__)


# ==========================================================
# OUTILS PAYDUNYA
# ==========================================================

def _paydunya_headers() -> dict[str, str]:
    """
    Construit les en-têtes d'authentification PayDunya.

    Les clés ne doivent jamais être journalisées.
    """
    return {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": settings.PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": settings.PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": settings.PAYDUNYA_TOKEN,
    }


def _paydunya_confirm_url(token: str) -> str:
    """
    Retourne l'endpoint de vérification selon le mode PayDunya.
    """
    mode = getattr(
        settings,
        "PAYDUNYA_MODE",
        "test",
    ).strip().lower()

    if mode == "live":
        base_url = (
            "https://app.paydunya.com/"
            "api/v1/checkout-invoice/confirm"
        )
    else:
        base_url = (
            "https://app.paydunya.com/"
            "sandbox-api/v1/checkout-invoice/confirm"
        )

    return f"{base_url}/{token}"


def _expected_hash() -> str:
    """
    Calcule le SHA-512 de la clé principale PayDunya.
    """
    master_key = settings.PAYDUNYA_MASTER_KEY

    return hashlib.sha512(
        master_key.encode("utf-8"),
    ).hexdigest()


def _normalise_status(status: Any) -> str:
    """
    Normalise les statuts reçus de PayDunya.
    """
    value = str(status or "").strip().lower()

    mapping = {
        "complete": "completed",
        "completed": "completed",
        "success": "completed",

        "pending": "pending",
        "processing": "pending",

        "cancel": "cancelled",
        "canceled": "cancelled",
        "cancelled": "cancelled",

        "fail": "failed",
        "failed": "failed",
        "failure": "failed",
    }

    return mapping.get(value, value)


def _decimal_amount(value: Any) -> Decimal | None:
    """
    Convertit proprement un montant PayDunya en Decimal.
    """
    if value in (None, ""):
        return None

    try:
        return Decimal(str(value)).quantize(
            Decimal("1"),
        )
    except (InvalidOperation, TypeError, ValueError):
        return None


def _extract_callback_payload(
    request: HttpRequest,
) -> dict[str, Any] | None:
    """
    PayDunya envoie généralement les données du callback dans
    request.POST["data"], sous forme de chaîne JSON.

    Cette fonction accepte également un dictionnaire déjà décodé
    ou un corps JSON afin de faciliter les tests.
    """
    raw_data = request.POST.get("data")

    if raw_data:
        if isinstance(raw_data, dict):
            return raw_data

        try:
            parsed = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Callback PayDunya : champ data JSON invalide.",
            )
            return None

        return parsed if isinstance(parsed, dict) else None

    # Tolérance pour certains environnements ou tests envoyant
    # directement un corps JSON.
    if request.body:
        try:
            parsed = json.loads(
                request.body.decode("utf-8"),
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
        ):
            return None

        if isinstance(parsed, dict):
            nested_data = parsed.get("data")

            if isinstance(nested_data, dict):
                return nested_data

            return parsed

    return None


def _extract_token(payload: dict[str, Any]) -> str:
    """
    Récupère le token de facture dans les différentes structures
    susceptibles d'être renvoyées par PayDunya.
    """
    invoice = payload.get("invoice") or {}

    if isinstance(invoice, dict):
        token = invoice.get("token")

        if token:
            return str(token).strip()

    return str(
        payload.get("token") or "",
    ).strip()


def _extract_total_amount(
    payload: dict[str, Any],
) -> Decimal | None:
    """
    Récupère le montant total de la facture.
    """
    invoice = payload.get("invoice") or {}

    if isinstance(invoice, dict):
        amount = _decimal_amount(
            invoice.get("total_amount"),
        )

        if amount is not None:
            return amount

    return _decimal_amount(
        payload.get("total_amount"),
    )


def _extract_receipt_url(
    payload: dict[str, Any],
) -> str:
    """
    Récupère l'URL du reçu électronique PayDunya.
    """
    receipt_url = (
        payload.get("receipt_url")
        or payload.get("receipt")
        or ""
    )

    invoice = payload.get("invoice") or {}

    if not receipt_url and isinstance(invoice, dict):
        receipt_url = (
            invoice.get("receipt_url")
            or invoice.get("receipt")
            or ""
        )

    return str(receipt_url or "").strip()


def _extract_customer(
    payload: dict[str, Any],
) -> dict[str, str]:
    """
    Extrait les coordonnées du client.
    """
    customer = payload.get("customer") or {}

    if not isinstance(customer, dict):
        customer = {}

    return {
        "name": str(
            customer.get("name") or "",
        ).strip(),
        "email": str(
            customer.get("email") or "",
        ).strip(),
        "phone": str(
            customer.get("phone") or "",
        ).strip(),
    }


def _confirm_invoice(
    token: str,
) -> tuple[bool, dict[str, Any]]:
    """
    Vérifie le statut réel de la facture auprès de PayDunya.

    Retour :
        (True, payload) si la requête PayDunya est valide ;
        (False, payload) en cas d'échec.
    """
    try:
        response = requests.get(
            _paydunya_confirm_url(token),
            headers=_paydunya_headers(),
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception(
            "Erreur réseau lors de la confirmation PayDunya : %s",
            exc,
        )

        return False, {
            "error": "PayDunya est momentanément indisponible.",
        }

    try:
        payload = response.json()
    except ValueError:
        logger.error(
            "Réponse PayDunya non JSON. HTTP=%s",
            response.status_code,
        )

        return False, {
            "error": "Réponse PayDunya invalide.",
        }

    if (
        response.status_code == 200
        and str(payload.get("response_code")) == "00"
    ):
        return True, payload

    logger.warning(
        "Échec confirmation PayDunya. HTTP=%s code=%s texte=%s",
        response.status_code,
        payload.get("response_code"),
        payload.get("response_text"),
    )

    return False, payload


def _verify_payload_hash(
    payload: dict[str, Any],
) -> bool:
    """
    Vérifie que le callback provient de PayDunya.
    """
    received_hash = str(
        payload.get("hash") or "",
    ).strip().lower()

    if not received_hash:
        return False

    return received_hash == _expected_hash().lower()


def _update_versement_from_payload(
    *,
    versement: Versement,
    payload: dict[str, Any],
    source: str,
) -> tuple[bool, str]:
    """
    Met à jour un versement à partir d'une réponse PayDunya.

    Cette fonction vérifie impérativement :
    - le token ;
    - le montant ;
    - le statut ;
    - l'idempotence.
    """
    token = _extract_token(payload)

    if not token or token != versement.paydunya_token:
        return False, "Token PayDunya incohérent."

    status = _normalise_status(
        payload.get("status"),
    )

    total_received = _extract_total_amount(payload)

    expected_amount = (
        Decimal(versement.montant or 0)
        + Decimal(versement.frais or 0)
    ).quantize(
        Decimal("1"),
    )

    if total_received is None:
        return False, "Montant PayDunya absent ou invalide."

    if total_received != expected_amount:
        logger.error(
            (
                "Montant PayDunya incohérent pour versement %s : "
                "attendu=%s reçu=%s"
            ),
            versement.id,
            expected_amount,
            total_received,
        )

        return False, "Montant PayDunya incohérent."

    # Une opération déjà validée ne doit jamais être déclassée
    # par un callback tardif ou dupliqué.
    if versement.statut == "VALIDE":
        versement.paydunya_payload = payload
        versement.save(
            update_fields=[
                "paydunya_payload",
            ],
        )

        return True, "Versement déjà validé."

    customer = _extract_customer(payload)
    receipt_url = _extract_receipt_url(payload)

    versement.paydunya_status = status
    versement.paydunya_payload = payload

    if receipt_url:
        versement.paydunya_receipt_url = receipt_url

    if customer["name"]:
        versement.paydunya_customer_name = customer["name"]

    if customer["phone"]:
        versement.paydunya_customer_phone = customer["phone"]

    if customer["email"]:
        versement.paydunya_customer_email = customer["email"]

    update_fields = [
        "paydunya_status",
        "paydunya_payload",
        "paydunya_receipt_url",
        "paydunya_customer_name",
        "paydunya_customer_phone",
        "paydunya_customer_email",
    ]

    if status == "completed":
        versement.statut = "VALIDE"
        versement.date_validation = timezone.now()
        versement.paydunya_paid_at = timezone.now()

        # La validation vient du prestataire, pas d'un admin.
        versement.valide_par = None

        update_fields.extend(
            [
                "statut",
                "date_validation",
                "paydunya_paid_at",
                "valide_par",
            ]
        )

        versement.save(
            update_fields=list(set(update_fields)),
        )

        logger.info(
            (
                "Versement PayDunya validé. "
                "versement_id=%s token=%s source=%s"
            ),
            versement.id,
            token,
            source,
        )

        return True, "Paiement confirmé."

    if status in {"cancelled", "failed"}:
        versement.statut = "REFUSE"
        versement.date_validation = timezone.now()

        update_fields.extend(
            [
                "statut",
                "date_validation",
            ]
        )

        versement.save(
            update_fields=list(set(update_fields)),
        )

        return True, "Paiement annulé ou échoué."

    # pending ou statut non final :
    # le versement demeure EN_ATTENTE.
    versement.statut = "EN_ATTENTE"

    update_fields.append("statut")

    versement.save(
        update_fields=list(set(update_fields)),
    )

    return True, "Paiement en attente."


# ==========================================================
# CALLBACK / IPN PAYDUNYA
# ==========================================================

@csrf_exempt
@require_POST
@transaction.atomic
def paydunya_callback(request: HttpRequest) -> HttpResponse:
    """
    Endpoint serveur-à-serveur appelé par PayDunya.

    Cette vue est exemptée de CSRF parce que PayDunya ne possède
    pas le cookie CSRF YAAYESS. La sécurité repose sur :
    - le hash SHA-512 ;
    - le token de facture ;
    - la vérification du montant ;
    - le verrouillage SQL ;
    - l'idempotence.
    """
    payload = _extract_callback_payload(request)

    if not payload:
        logger.warning(
            "Callback PayDunya reçu sans payload exploitable.",
        )

        return HttpResponseBadRequest(
            "Payload PayDunya invalide.",
        )

    if not _verify_payload_hash(payload):
        logger.warning(
            "Callback PayDunya rejeté : hash invalide.",
        )

        return JsonResponse(
            {
                "success": False,
                "error": "Signature PayDunya invalide.",
            },
            status=403,
        )

    token = _extract_token(payload)

    if not token:
        return HttpResponseBadRequest(
            "Token PayDunya absent.",
        )

    try:
        versement = (
            Versement.objects
            .select_for_update()
            .select_related(
                "member__group",
                "member__user",
            )
            .get(
                paydunya_token=token,
                methode="PAYDUNYA",
            )
        )
    except Versement.DoesNotExist:
        logger.warning(
            "Callback PayDunya : token inconnu %s",
            token,
        )

        return JsonResponse(
            {
                "success": False,
                "error": "Transaction YAAYESS introuvable.",
            },
            status=404,
        )

    success, message = _update_versement_from_payload(
        versement=versement,
        payload=payload,
        source="callback",
    )

    if not success:
        return JsonResponse(
            {
                "success": False,
                "error": message,
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            "message": message,
            "versement_id": versement.id,
            "status": versement.paydunya_status,
        },
    )


# ==========================================================
# RETOUR APRÈS PAIEMENT
# ==========================================================

@require_GET
@transaction.atomic
def paydunya_return(request: HttpRequest) -> HttpResponse:
    """
    Retour navigateur après paiement.

    Le retour navigateur ne fait jamais confiance à un simple
    paramètre de succès. Il interroge PayDunya avec le token afin
    de connaître le statut réel de la facture.
    """
    token = (
        request.GET.get("token") or ""
    ).strip()

    if not token:
        messages.error(
            request,
            "Token de paiement PayDunya manquant.",
        )

        return redirect(
            "cotisationtontine:dashboard_tontine_simple",
        )

    try:
        versement = (
            Versement.objects
            .select_for_update()
            .select_related(
                "member__group",
                "member__user",
            )
            .get(
                paydunya_token=token,
                methode="PAYDUNYA",
            )
        )
    except Versement.DoesNotExist:
        messages.error(
            request,
            "Transaction PayDunya introuvable.",
        )

        return redirect(
            "cotisationtontine:dashboard_tontine_simple",
        )

    confirmed, payload = _confirm_invoice(token)

    if not confirmed:
        messages.warning(
            request,
            (
                "Le statut du paiement ne peut pas encore être "
                "confirmé. La vérification sera réessayée par "
                "la notification PayDunya."
            ),
        )

        return render(
            request,
            "cotisationtontine/paydunya_return.html",
            {
                "versement": versement,
                "payment_status": "pending",
                "paydunya_response": payload,
            },
        )

    if not _verify_payload_hash(payload):
        logger.warning(
            "Retour PayDunya rejeté : hash de confirmation invalide.",
        )

        messages.error(
            request,
            "La réponse de confirmation PayDunya est invalide.",
        )

        return render(
            request,
            "cotisationtontine/paydunya_return.html",
            {
                "versement": versement,
                "payment_status": "error",
            },
            status=400,
        )

    success, message = _update_versement_from_payload(
        versement=versement,
        payload=payload,
        source="return",
    )

    versement.refresh_from_db()

    if not success:
        messages.error(
            request,
            message,
        )

        payment_status = "error"

    elif versement.paydunya_status == "completed":
        messages.success(
            request,
            "Votre paiement a été confirmé avec succès.",
        )

        payment_status = "completed"

    elif versement.paydunya_status in {
        "cancelled",
        "failed",
    }:
        messages.error(
            request,
            "Le paiement a été annulé ou a échoué.",
        )

        payment_status = versement.paydunya_status

    else:
        messages.info(
            request,
            "Votre paiement est encore en cours de traitement.",
        )

        payment_status = "pending"

    return render(
        request,
        "cotisationtontine/paydunya_return.html",
        {
            "versement": versement,
            "group": versement.member.group,
            "payment_status": payment_status,
            "receipt_url": versement.paydunya_receipt_url,
        },
    )


# ==========================================================
# ANNULATION DU PAIEMENT
# ==========================================================

@require_GET
@transaction.atomic
def paydunya_cancel(request: HttpRequest) -> HttpResponse:
    """
    Retour navigateur lorsqu'un client annule le paiement.

    L'annulation navigateur n'est pas utilisée comme preuve
    définitive : la facture est vérifiée auprès de PayDunya.
    """
    token = (
        request.GET.get("token") or ""
    ).strip()

    if not token:
        messages.warning(
            request,
            "Le paiement a été interrompu.",
        )

        return redirect(
            "cotisationtontine:dashboard_tontine_simple",
        )

    try:
        versement = (
            Versement.objects
            .select_for_update()
            .select_related(
                "member__group",
                "member__user",
            )
            .get(
                paydunya_token=token,
                methode="PAYDUNYA",
            )
        )
    except Versement.DoesNotExist:
        messages.error(
            request,
            "Transaction PayDunya introuvable.",
        )

        return redirect(
            "cotisationtontine:dashboard_tontine_simple",
        )

    confirmed, payload = _confirm_invoice(token)

    if confirmed and _verify_payload_hash(payload):
        _update_versement_from_payload(
            versement=versement,
            payload=payload,
            source="cancel",
        )

        versement.refresh_from_db()

    # Ne jamais annuler une opération déjà confirmée.
    if versement.statut == "VALIDE":
        messages.success(
            request,
            (
                "Le paiement avait déjà été confirmé. "
                "Votre versement reste validé."
            ),
        )
    else:
        messages.warning(
            request,
            "Le paiement PayDunya a été annulé ou interrompu.",
        )

    return render(
        request,
        "cotisationtontine/paydunya_cancel.html",
        {
            "versement": versement,
            "group": versement.member.group,
            "payment_status": versement.paydunya_status,
        },
    )

# ==========================================================
# INITIATION DU PAIEMENT PAYDUNYA
# ==========================================================

@login_required
@require_POST
@transaction.atomic
def paydunya_initier(request, member_id):
    """
    Crée un versement PayDunya en attente, génère une facture
    PayDunya et redirige l'utilisateur vers la page de paiement.
    """

    member = get_object_or_404(
        GroupMember.objects
        .select_for_update()
        .select_related("group", "user"),
        id=member_id,
    )

    group = member.group

    # ======================================================
    # CONTRÔLE D'ACCÈS
    # ======================================================

    user_is_admin = (
        request.user == group.admin
        or request.user.is_superuser
    )

    if not user_is_admin and request.user != member.user:
        messages.error(
            request,
            "Vous ne pouvez effectuer un paiement que pour vous-même.",
        )

        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # CONTRÔLE DU CYCLE
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
            "Le cycle est terminé. Aucun paiement ne peut être initié.",
        )

        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # MONTANT SAISI
    # ======================================================

    montant_raw = (
        request.POST.get("montant") or ""
    ).replace(",", ".").strip()

    try:
        montant = Decimal(montant_raw)
    except (InvalidOperation, TypeError, ValueError):
        messages.error(
            request,
            "Le montant saisi est invalide.",
        )

        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member.id,
        )

    montant = montant.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    if montant <= 0:
        messages.error(
            request,
            "Le montant doit être supérieur à zéro.",
        )

        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member.id,
        )

    # ======================================================
    # MONTANT MINIMUM PAYDUNYA
    # ======================================================

    MONTANT_MINIMUM_PAYDUNYA = Decimal("1000")

    if montant < MONTANT_MINIMUM_PAYDUNYA:
        messages.error(
            request,
            (
                "Le montant minimum pour un paiement PayDunya "
                "est de 1 000 FCFA. "
                "Pour un montant inférieur, veuillez utiliser "
                "le paiement en caisse."
            ),
        )

        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member.id,
        )

    # ======================================================
    # CALCUL DU RESTE À PAYER
    # ======================================================

    total_engage = (
        Versement.objects
        .filter(
            member=member,
            statut__in=["EN_ATTENTE", "VALIDE"],
            cycle=group.cycle_numero,
            tour=group.tour_actuel,
        )
        .aggregate(total=Sum("montant"))["total"]
        or Decimal("0")
    )

    montant_base = Decimal(
        str(group.montant_base or 0)
    )

    reste = montant_base - total_engage

    if reste <= 0:
        messages.info(
            request,
            "Le montant du tour est déjà entièrement payé.",
        )

        return redirect(
            "cotisationtontine:group_detail",
            group_id=group.id,
        )

    if montant > reste:
        messages.error(
            request,
            f"Le montant dépasse le reste à payer : {reste} FCFA.",
        )

        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member.id,
        )

    # ======================================================
    # FRAIS YAAYESS
    # ======================================================

    frais = (
        montant * Decimal("0.03")
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    # ======================================================
    # CRÉATION DU VERSEMENT LOCAL
    # ======================================================

    versement = Versement.objects.create(
        member=member,
        montant=montant,
        frais=frais,
        methode="PAYDUNYA",
        statut="EN_ATTENTE",
        cycle=group.cycle_numero,
        tour=group.tour_actuel,
        paydunya_status="pending",
    )

    # ======================================================
    # CRÉATION DE LA FACTURE PAYDUNYA
    # ======================================================

    return_url = request.build_absolute_uri(
        reverse(
            "cotisationtontine:paydunya_return"
        )
    )

    cancel_url = request.build_absolute_uri(
        reverse(
            "cotisationtontine:paydunya_cancel"
        )
    )

    callback_url = request.build_absolute_uri(
        reverse(
            "cotisationtontine:paydunya_callback"
        )
    )

    logger.info(
        (
            "Initialisation PayDunya. "
            "versement_id=%s return_url=%s "
            "cancel_url=%s callback_url=%s"
        ),
        versement.id,
        return_url,
        cancel_url,
        callback_url,
    )

    try:
        token, checkout_url, response_payload = (
            create_checkout_invoice(
                versement=versement,
                return_url=return_url,
                cancel_url=cancel_url,
                callback_url=callback_url,
            )
        )

    except PayDunyaConfigurationError as exc:
        versement.delete()

        messages.error(
            request,
            f"Configuration PayDunya invalide : {exc}",
        )

        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member.id,
        )

    except PayDunyaAPIError as exc:
        versement.delete()

        messages.error(
            request,
            f"Impossible d'initier le paiement PayDunya : {exc}",
        )

        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member.id,
        )

    except Exception:
        logger.exception(
            "Erreur technique pendant l'initialisation PayDunya."
        )

        versement.delete()

        messages.error(
            request,
            (
                "Une erreur technique est survenue pendant "
                "l'initialisation du paiement."
            ),
        )

        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member.id,
        )

    if not checkout_url:
        versement.delete()

        messages.error(
            request,
            "PayDunya n'a pas fourni d'adresse de paiement.",
        )

        return redirect(
            "cotisationtontine:initier_versement",
            member_id=member.id,
        )

    return redirect(checkout_url)
