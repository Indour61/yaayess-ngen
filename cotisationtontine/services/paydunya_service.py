import hashlib
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from cotisationtontine.models import Versement


logger = logging.getLogger(__name__)


class PayDunyaError(Exception):
    """
    Erreur fonctionnelle ou technique liée à PayDunya.
    """


class PayDunyaConfigurationError(PayDunyaError):
    """
    Configuration PayDunya absente ou invalide.
    """


class PayDunyaAPIError(PayDunyaError):
    """
    Réponse invalide ou négative de l'API PayDunya.
    """


class PayDunyaAmountError(PayDunyaError):
    """
    Incohérence entre le montant YAAYESS et le montant PayDunya.
    """


# ==========================================================
# CONFIGURATION
# ==========================================================

def get_paydunya_mode() -> str:
    mode = str(
        getattr(settings, "PAYDUNYA_MODE", "test")
    ).strip().lower()

    if mode not in {"test", "live"}:
        raise PayDunyaConfigurationError(
            "PAYDUNYA_MODE doit être égal à 'test' ou 'live'."
        )

    return mode


def validate_paydunya_settings() -> None:
    required_settings = (
        "PAYDUNYA_MASTER_KEY",
        "PAYDUNYA_PRIVATE_KEY",
        "PAYDUNYA_TOKEN",
    )

    missing = [
        name
        for name in required_settings
        if not str(getattr(settings, name, "")).strip()
    ]

    if missing:
        raise PayDunyaConfigurationError(
            "Configuration PayDunya incomplète : "
            + ", ".join(missing)
        )


def get_api_base_url() -> str:
    if get_paydunya_mode() == "live":
        return "https://app.paydunya.com/api/v1"

    return "https://app.paydunya.com/sandbox-api/v1"


def get_create_invoice_url() -> str:
    return f"{get_api_base_url()}/checkout-invoice/create"


def get_confirm_invoice_url(token: str) -> str:
    token = str(token or "").strip()

    if not token:
        raise PayDunyaAPIError(
            "Le token PayDunya est obligatoire."
        )

    return (
        f"{get_api_base_url()}/checkout-invoice/confirm/"
        f"{token}"
    )


def get_paydunya_headers() -> dict[str, str]:
    validate_paydunya_settings()

    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "PAYDUNYA-MASTER-KEY": settings.PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": settings.PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": settings.PAYDUNYA_TOKEN,
    }


# ==========================================================
# OUTILS
# ==========================================================

def calculate_expected_amount(
    versement: Versement,
) -> Decimal:
    montant = Decimal(
        str(versement.montant or 0)
    )

    frais = Decimal(
        str(versement.frais or 0)
    )

    return (montant + frais).quantize(
        Decimal("1")
    )


def decimal_amount(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None

    try:
        return Decimal(
            str(value)
        ).quantize(
            Decimal("1")
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return None


def expected_callback_hash() -> str:
    validate_paydunya_settings()

    master_key = settings.PAYDUNYA_MASTER_KEY

    return hashlib.sha512(
        master_key.encode("utf-8")
    ).hexdigest()


def verify_callback_hash(received_hash: str) -> bool:
    received_hash = str(
        received_hash or ""
    ).strip().lower()

    if not received_hash:
        return False

    return received_hash == expected_callback_hash().lower()


def normalize_status(status: Any) -> str:
    value = str(
        status or ""
    ).strip().lower()

    aliases = {
        "complete": "completed",
        "success": "completed",
        "completed": "completed",

        "processing": "pending",
        "pending": "pending",

        "cancel": "cancelled",
        "canceled": "cancelled",
        "cancelled": "cancelled",

        "fail": "failed",
        "failure": "failed",
        "failed": "failed",
    }

    return aliases.get(value, value)


def extract_invoice_token(
    payload: dict[str, Any],
) -> str:
    invoice = payload.get("invoice") or {}

    if isinstance(invoice, dict):
        token = invoice.get("token")

        if token:
            return str(token).strip()

    return str(
        payload.get("token") or ""
    ).strip()


def extract_total_amount(
    payload: dict[str, Any],
) -> Decimal | None:
    invoice = payload.get("invoice") or {}

    if isinstance(invoice, dict):
        total = decimal_amount(
            invoice.get("total_amount")
        )

        if total is not None:
            return total

    return decimal_amount(
        payload.get("total_amount")
    )


def extract_receipt_url(
    payload: dict[str, Any],
) -> str:
    receipt_url = str(
        payload.get("receipt_url") or ""
    ).strip()

    if receipt_url:
        return receipt_url

    invoice = payload.get("invoice") or {}

    if isinstance(invoice, dict):
        return str(
            invoice.get("receipt_url") or ""
        ).strip()

    return ""


def extract_customer(
    payload: dict[str, Any],
) -> dict[str, str]:
    customer = payload.get("customer") or {}

    if not isinstance(customer, dict):
        customer = {}

    return {
        "name": str(
            customer.get("name") or ""
        ).strip(),
        "email": str(
            customer.get("email") or ""
        ).strip(),
        "phone": str(
            customer.get("phone") or ""
        ).strip(),
    }


def validate_invoice_amount(
    versement: Versement,
    payload: dict[str, Any],
) -> Decimal:
    received_amount = extract_total_amount(
        payload
    )

    if received_amount is None:
        raise PayDunyaAmountError(
            "Le montant PayDunya est absent ou invalide."
        )

    expected_amount = calculate_expected_amount(
        versement
    )

    if received_amount != expected_amount:
        logger.error(
            (
                "Montant PayDunya incohérent. "
                "versement_id=%s attendu=%s reçu=%s"
            ),
            versement.id,
            expected_amount,
            received_amount,
        )

        raise PayDunyaAmountError(
            "Le montant PayDunya ne correspond pas "
            "au montant attendu par YAAYESS."
        )

    return received_amount


# ==========================================================
# CONSTRUCTION DE LA FACTURE
# ==========================================================

def build_invoice_payload(
    versement: Versement,
    *,
    return_url: str = "",
    cancel_url: str = "",
    callback_url: str = "",
) -> dict[str, Any]:
    member = versement.member
    group = member.group
    user = member.user

    montant = Decimal(
        str(versement.montant or 0)
    ).quantize(
        Decimal("1")
    )

    frais = Decimal(
        str(versement.frais or 0)
    ).quantize(
        Decimal("1")
    )

    total_amount = calculate_expected_amount(
        versement
    )

    customer_name = (
        getattr(user, "nom", "")
        or getattr(user, "get_full_name", lambda: "")()
        or member.alias
        or getattr(user, "phone", "")
        or "Membre YAAYESS"
    )

    customer_phone = str(
        getattr(user, "phone", "") or ""
    ).strip()

    customer_email = str(
        getattr(user, "email", "") or ""
    ).strip()

    payload = {
        "invoice": {
            "items": {
                "item_0": {
                    "name": (
                        f"Cotisation tontine — {group.nom}"
                    ),
                    "quantity": 1,
                    "unit_price": int(montant),
                    "total_price": int(montant),
                    "description": (
                        f"Cycle {versement.cycle}, "
                        f"tour {versement.tour}"
                    ),
                },
            },
            "taxes": {
                "tax_0": {
                    "name": "Frais de service YAAYESS (3 %)",
                    "amount": int(frais),
                },
            },
            "customer": {
                "name": str(customer_name),
                "email": customer_email,
                "phone": customer_phone,
            },
            "total_amount": int(total_amount),
            "description": (
                f"Versement YAAYESS de {int(montant)} FCFA "
                f"pour le groupe {group.nom}"
            ),
        },
        "store": {
            "name": getattr(
                settings,
                "PAYDUNYA_STORE_NAME",
                "YAAYESS",
            ),
            "tagline": getattr(
                settings,
                "PAYDUNYA_STORE_TAGLINE",
                "",
            ),
            "phone": getattr(
                settings,
                "PAYDUNYA_STORE_PHONE",
                "",
            ),
            "website_url": getattr(
                settings,
                "PAYDUNYA_STORE_WEBSITE",
                "",
            ),
            "logo_url": getattr(
                settings,
                "PAYDUNYA_STORE_LOGO",
                "",
            ),
        },
        "custom_data": {
            "versement_id": versement.id,
            "group_id": group.id,
            "member_id": member.id,
            "cycle": versement.cycle,
            "tour": versement.tour,
            "montant_cotisation": int(montant),
            "frais_yaayess": int(frais),
        },
        "actions": {
            "return_url": (
                str(return_url or "").strip()
                or str(
                    getattr(
                        settings,
                        "PAYDUNYA_RETURN_URL",
                        "",
                    )
                    or ""
                ).strip()
            ),
            "cancel_url": (
                str(cancel_url or "").strip()
                or str(
                    getattr(
                        settings,
                        "PAYDUNYA_CANCEL_URL",
                        "",
                    )
                    or ""
                ).strip()
            ),
            "callback_url": (
                str(callback_url or "").strip()
                or str(
                    getattr(
                        settings,
                        "PAYDUNYA_CALLBACK_URL",
                        "",
                    )
                    or ""
                ).strip()
            ),
        },
    }

    return payload


# ==========================================================
# CRÉATION DE FACTURE
# ==========================================================

@transaction.atomic
def create_checkout_invoice(
    versement: Versement,
    *,
    return_url: str = "",
    cancel_url: str = "",
    callback_url: str = "",
) -> tuple[str, str, dict[str, Any]]:
    """
    Crée une facture PayDunya.

    Retourne :
        token,
        checkout_url,
        payload PayDunya.
    """

    versement = (
        Versement.objects
        .select_for_update()
        .select_related(
            "member__group",
            "member__user",
        )
        .get(pk=versement.pk)
    )

    if versement.statut == "VALIDE":
        raise PayDunyaAPIError(
            "Ce versement est déjà validé."
        )

    if (
        versement.paydunya_token
        and versement.paydunya_invoice_url
        and versement.paydunya_status == "pending"
    ):
        return (
            versement.paydunya_token,
            versement.paydunya_invoice_url,
            versement.paydunya_payload or {},
        )

    payload = build_invoice_payload(
        versement,
        return_url=return_url,
        cancel_url=cancel_url,
        callback_url=callback_url,
    )

    actions = payload.get("actions") or {}

    if not actions.get("return_url"):
        raise PayDunyaConfigurationError(
            "L'URL de retour PayDunya est absente."
        )

    if not actions.get("cancel_url"):
        raise PayDunyaConfigurationError(
            "L'URL d'annulation PayDunya est absente."
        )

    if (
        get_paydunya_mode() == "live"
        and not actions.get("callback_url")
    ):
        raise PayDunyaConfigurationError(
            "L'URL callback PayDunya est absente en mode live."
        )

    try:
        response = requests.post(
            get_create_invoice_url(),
            headers=get_paydunya_headers(),
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception(
            "Erreur réseau lors de la création PayDunya."
        )

        raise PayDunyaAPIError(
            "PayDunya est momentanément indisponible."
        ) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        logger.error(
            "Réponse PayDunya non JSON. HTTP=%s",
            response.status_code,
        )

        raise PayDunyaAPIError(
            "PayDunya a renvoyé une réponse invalide."
        ) from exc

    response_code = str(
        response_payload.get("response_code") or ""
    )

    if (
        response.status_code not in {200, 201}
        or response_code != "00"
    ):
        logger.warning(
            (
                "Échec création facture PayDunya. "
                "HTTP=%s code=%s texte=%s"
            ),
            response.status_code,
            response_code,
            response_payload.get("response_text"),
        )

        raise PayDunyaAPIError(
            response_payload.get("response_text")
            or "Impossible de créer la facture PayDunya."
        )

    token = str(
        response_payload.get("token") or ""
    ).strip()

    checkout_url = str(
        response_payload.get("response_text") or ""
    ).strip()

    if not token or not checkout_url:
        raise PayDunyaAPIError(
            "La réponse PayDunya ne contient pas "
            "le token ou l'URL de paiement."
        )

    user = versement.member.user

    versement.methode = "PAYDUNYA"
    versement.paydunya_token = token
    versement.paydunya_status = "pending"
    versement.paydunya_invoice_url = checkout_url
    versement.paydunya_payload = response_payload

    versement.paydunya_customer_name = (
        getattr(user, "nom", "")
        or versement.member.alias
        or getattr(user, "phone", "")
        or ""
    )

    versement.paydunya_customer_phone = str(
        getattr(user, "phone", "") or ""
    )

    versement.paydunya_customer_email = str(
        getattr(user, "email", "") or ""
    )

    versement.save(
        update_fields=[
            "methode",
            "paydunya_token",
            "paydunya_status",
            "paydunya_invoice_url",
            "paydunya_payload",
            "paydunya_customer_name",
            "paydunya_customer_phone",
            "paydunya_customer_email",
        ]
    )

    return token, checkout_url, response_payload


# ==========================================================
# VÉRIFICATION D'UNE FACTURE
# ==========================================================

def confirm_checkout_invoice(
    token: str,
) -> dict[str, Any]:
    try:
        response = requests.get(
            get_confirm_invoice_url(token),
            headers=get_paydunya_headers(),
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception(
            "Erreur réseau de confirmation PayDunya."
        )

        raise PayDunyaAPIError(
            "Impossible de vérifier le paiement PayDunya."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise PayDunyaAPIError(
            "Réponse de confirmation PayDunya invalide."
        ) from exc

    if (
        response.status_code != 200
        or str(payload.get("response_code") or "") != "00"
    ):
        raise PayDunyaAPIError(
            payload.get("response_text")
            or "Transaction PayDunya introuvable."
        )

    return payload


# ==========================================================
# SYNCHRONISATION DU VERSEMENT
# ==========================================================

@transaction.atomic
def synchronize_versement(
    versement: Versement,
    payload: dict[str, Any],
    *,
    source: str = "confirmation",
) -> Versement:
    versement = (
        Versement.objects
        .select_for_update()
        .select_related(
            "member__group",
            "member__user",
        )
        .get(pk=versement.pk)
    )

    token = extract_invoice_token(
        payload
    )

    if (
        not token
        or token != versement.paydunya_token
    ):
        raise PayDunyaAPIError(
            "Token PayDunya incohérent."
        )

    validate_invoice_amount(
        versement,
        payload,
    )

    status = normalize_status(
        payload.get("status")
    )

    customer = extract_customer(
        payload
    )

    receipt_url = extract_receipt_url(
        payload
    )

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

    update_fields = {
        "paydunya_status",
        "paydunya_payload",
        "paydunya_receipt_url",
        "paydunya_customer_name",
        "paydunya_customer_phone",
        "paydunya_customer_email",
    }

    if status == "completed":
        if versement.statut != "VALIDE":
            now = timezone.now()

            versement.statut = "VALIDE"
            versement.date_validation = now
            versement.paydunya_paid_at = now
            versement.valide_par = None

            update_fields.update(
                {
                    "statut",
                    "date_validation",
                    "paydunya_paid_at",
                    "valide_par",
                }
            )

    elif status in {"cancelled", "failed"}:
        if versement.statut != "VALIDE":
            versement.statut = "REFUSE"
            versement.date_validation = timezone.now()

            update_fields.update(
                {
                    "statut",
                    "date_validation",
                }
            )

    elif versement.statut != "VALIDE":
        versement.statut = "EN_ATTENTE"
        update_fields.add("statut")

    versement.save(
        update_fields=sorted(update_fields)
    )

    logger.info(
        (
            "Synchronisation PayDunya. "
            "versement_id=%s statut=%s source=%s"
        ),
        versement.id,
        status,
        source,
    )

    return versement