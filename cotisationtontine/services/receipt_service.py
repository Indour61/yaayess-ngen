import logging
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlparse

from django.db import transaction

from cotisationtontine.models import Versement
from cotisationtontine.services.paydunya_service import (
    PayDunyaAPIError,
    calculate_expected_amount,
    confirm_checkout_invoice,
    synchronize_versement,
)


logger = logging.getLogger(__name__)


class ReceiptError(Exception):
    """
    Erreur liée au reçu d'un paiement.
    """


class ReceiptUnavailableError(ReceiptError):
    """
    Le reçu n'est pas encore disponible.
    """


@dataclass(frozen=True)
class ReceiptData:
    versement_id: int
    token: str
    group_name: str
    member_name: str
    member_phone: str
    montant: Decimal
    frais: Decimal
    total: Decimal
    cycle: int
    tour: int
    payment_status: str
    receipt_url: str
    paid_at: object


# ==========================================================
# VALIDATION DE L'URL DU REÇU
# ==========================================================

def is_valid_paydunya_receipt_url(
    receipt_url: str,
) -> bool:
    """
    Évite d'exposer une URL arbitraire enregistrée dans la base.
    """

    if not receipt_url:
        return False

    parsed = urlparse(
        receipt_url
    )

    if parsed.scheme != "https":
        return False

    hostname = (
        parsed.hostname or ""
    ).lower()

    allowed_hosts = {
        "paydunya.com",
        "www.paydunya.com",
        "app.paydunya.com",
    }

    return (
        hostname in allowed_hosts
        or hostname.endswith(".paydunya.com")
    )


# ==========================================================
# SYNCHRONISATION DU REÇU
# ==========================================================

@transaction.atomic
def refresh_paydunya_receipt(
    versement: Versement,
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

    if versement.methode != "PAYDUNYA":
        raise ReceiptUnavailableError(
            "Ce versement n'a pas été effectué via PayDunya."
        )

    if not versement.paydunya_token:
        raise ReceiptUnavailableError(
            "Ce versement ne possède pas de token PayDunya."
        )

    try:
        payload = confirm_checkout_invoice(
            versement.paydunya_token
        )
    except PayDunyaAPIError as exc:
        raise ReceiptError(
            str(exc)
        ) from exc

    versement = synchronize_versement(
        versement,
        payload,
        source="receipt_refresh",
    )

    return versement


# ==========================================================
# DONNÉES DU REÇU
# ==========================================================

def get_receipt_data(
    versement: Versement,
    *,
    refresh: bool = False,
) -> ReceiptData:
    if refresh:
        versement = refresh_paydunya_receipt(
            versement
        )
    else:
        versement = (
            Versement.objects
            .select_related(
                "member__group",
                "member__user",
            )
            .get(pk=versement.pk)
        )

    if versement.methode != "PAYDUNYA":
        raise ReceiptUnavailableError(
            "Ce versement n'a pas été payé via PayDunya."
        )

    if (
        versement.statut != "VALIDE"
        or versement.paydunya_status != "completed"
    ):
        raise ReceiptUnavailableError(
            "Le paiement n'est pas encore confirmé."
        )

    receipt_url = str(
        versement.paydunya_receipt_url or ""
    ).strip()

    if not is_valid_paydunya_receipt_url(
        receipt_url
    ):
        raise ReceiptUnavailableError(
            "Le reçu PayDunya n'est pas encore disponible."
        )

    user = versement.member.user

    member_name = (
        getattr(user, "nom", "")
        or versement.member.alias
        or getattr(user, "phone", "")
        or "Membre YAAYESS"
    )

    member_phone = str(
        getattr(user, "phone", "") or ""
    )

    return ReceiptData(
        versement_id=versement.id,
        token=versement.paydunya_token,
        group_name=versement.member.group.nom,
        member_name=str(member_name),
        member_phone=member_phone,
        montant=Decimal(
            str(versement.montant or 0)
        ),
        frais=Decimal(
            str(versement.frais or 0)
        ),
        total=calculate_expected_amount(
            versement
        ),
        cycle=versement.cycle,
        tour=versement.tour,
        payment_status=versement.paydunya_status,
        receipt_url=receipt_url,
        paid_at=versement.paydunya_paid_at,
    )


# ==========================================================
# CONTEXTE POUR LE TEMPLATE
# ==========================================================

def build_receipt_context(
    versement: Versement,
    *,
    refresh: bool = False,
) -> dict:
    receipt = get_receipt_data(
        versement,
        refresh=refresh,
    )

    return {
        "versement": versement,
        "receipt": receipt,
        "receipt_url": receipt.receipt_url,
        "montant": receipt.montant,
        "frais": receipt.frais,
        "total": receipt.total,
        "group_name": receipt.group_name,
        "member_name": receipt.member_name,
        "member_phone": receipt.member_phone,
        "cycle": receipt.cycle,
        "tour": receipt.tour,
        "paid_at": receipt.paid_at,
    }