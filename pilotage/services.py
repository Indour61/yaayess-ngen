from __future__ import annotations

import unicodedata
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone

from accounts.models import CustomUser
from cotisationtontine.models import (
    Group as TontineGroup,
    GroupMember as TontineGroupMember,
    Versement as TontineVersement,
)
from epargnecredit.models import (
    Group as EpargneGroup,
    GroupMember as EpargneGroupMember,
    PretDemande,
    PretRemboursement,
    Versement as EpargneVersement,
)


SUCCESS_STATUS_WORDS = {
    "valide",
    "validee",
    "valider",
    "approved",
    "approuve",
    "accepte",
    "paid",
    "paye",
    "success",
    "successful",
    "completed",
    "complete",
    "termine",
}


def normalize_text(value: Any) -> str:
    """
    Normalise une valeur pour comparer les statuts,
    y compris les accents et les majuscules.
    """
    text = str(value or "").strip().lower()

    return "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )


def get_success_statuses(model, field_name: str = "statut") -> list[str]:
    """
    Détecte automatiquement les valeurs considérées comme validées
    à partir des choices du champ statut.
    """
    field = model._meta.get_field(field_name)
    success_values: list[str] = []

    for value, label in field.flatchoices:
        normalized_value = normalize_text(value)
        normalized_label = normalize_text(label)

        if any(
            word in normalized_value or word in normalized_label
            for word in SUCCESS_STATUS_WORDS
        ):
            success_values.append(value)

    if success_values:
        return success_values

    # Valeurs de secours si le champ n'utilise pas choices.
    return [
        "VALIDE",
        "VALIDEE",
        "APPROVED",
        "APPROUVE",
        "PAID",
        "SUCCESS",
        "COMPLETED",
    ]


def make_datetime_range(start_date, end_date):
    """
    Transforme deux dates en intervalle datetime compatible
    avec les champs DateTimeField.
    """
    current_timezone = timezone.get_current_timezone()

    start_datetime = timezone.make_aware(
        datetime.combine(start_date, time.min),
        current_timezone,
    )

    end_datetime = timezone.make_aware(
        datetime.combine(end_date, time.max),
        current_timezone,
    )

    return start_datetime, end_datetime


def decimal_value(value) -> Decimal:
    return value if value is not None else Decimal("0")


def percentage(part: int, total: int) -> float:
    if total <= 0:
        return 100.0

    return round((part / total) * 100, 2)


def get_live_dashboard_metrics(dashboard) -> dict[str, Any]:
    """
    Calcule les KPI de la période du tableau de bord
    directement depuis la base de données.
    """
    start_date = dashboard.period_start
    end_date = dashboard.period_end

    start_datetime, end_datetime = make_datetime_range(
        start_date,
        end_date,
    )

    # ==========================================================
    # STATUTS VALIDÉS
    # ==========================================================

    tontine_success_statuses = get_success_statuses(
        TontineVersement
    )

    epargne_success_statuses = get_success_statuses(
        EpargneVersement
    )

    credit_success_statuses = get_success_statuses(
        PretDemande
    )

    repayment_success_statuses = get_success_statuses(
        PretRemboursement
    )

    # ==========================================================
    # UTILISATEURS
    # ==========================================================

    accounts_created = CustomUser.objects.filter(
        created_at__range=(start_datetime, end_datetime),
    ).count()

    active_users = CustomUser.objects.filter(
        is_active=True,
        last_login__range=(start_datetime, end_datetime),
    ).count()

    total_active_accounts = CustomUser.objects.filter(
        is_active=True,
    ).count()

    # ==========================================================
    # GROUPES
    # ==========================================================

    tontine_groups_created = TontineGroup.objects.filter(
        date_creation__range=(start_datetime, end_datetime),
    ).count()

    epargne_groups_created = EpargneGroup.objects.filter(
        date_creation__range=(start_datetime, end_datetime),
    ).count()

    groups_created = (
        tontine_groups_created
        + epargne_groups_created
    )

    total_groups = (
        TontineGroup.objects.filter(is_active=True).count()
        + EpargneGroup.objects.filter(is_active=True).count()
    )

    # ==========================================================
    # MEMBRES
    # ==========================================================

    tontine_member_ids = set(
        TontineGroupMember.objects.filter(
            actif=True,
            date_ajout__range=(start_datetime, end_datetime),
        ).values_list("user_id", flat=True)
    )

    epargne_member_ids = set(
        EpargneGroupMember.objects.filter(
            actif=True,
            date_ajout__range=(start_datetime, end_datetime),
        ).values_list("user_id", flat=True)
    )

    registered_members = len(
        tontine_member_ids | epargne_member_ids
    )

    total_member_ids = set(
        TontineGroupMember.objects.filter(
            actif=True,
        ).values_list("user_id", flat=True)
    )

    total_member_ids.update(
        EpargneGroupMember.objects.filter(
            actif=True,
        ).values_list("user_id", flat=True)
    )

    total_registered_members = len(total_member_ids)

    # ==========================================================
    # TONTINES / COTISATIONS
    # ==========================================================

    tontine_operations = TontineVersement.objects.filter(
        date_creation__range=(start_datetime, end_datetime),
    )

    validated_tontine_operations = tontine_operations.filter(
        statut__in=tontine_success_statuses,
    )

    tontine_summary = validated_tontine_operations.aggregate(
        operation_count=Count("id"),
        total_amount=Sum("montant"),
    )

    contributions_count = (
        tontine_summary["operation_count"] or 0
    )

    contributions_amount = decimal_value(
        tontine_summary["total_amount"]
    )

    # ==========================================================
    # ÉPARGNE
    # ==========================================================

    savings_operations = EpargneVersement.objects.filter(
        date_creation__range=(start_datetime, end_datetime),
    )

    validated_savings_operations = savings_operations.filter(
        statut__in=epargne_success_statuses,
    )

    savings_summary = validated_savings_operations.aggregate(
        operation_count=Count("id"),
        total_amount=Sum("montant"),
    )

    savings_deposits_count = (
        savings_summary["operation_count"] or 0
    )

    savings_amount = decimal_value(
        savings_summary["total_amount"]
    )

    # ==========================================================
    # CRÉDITS
    # ==========================================================

    credit_requests = PretDemande.objects.filter(
        created_at__range=(start_datetime, end_datetime),
    )

    approved_credits = credit_requests.filter(
        statut__in=credit_success_statuses,
    )

    credit_summary = approved_credits.aggregate(
        credit_count=Count("id"),
        total_amount=Sum("montant"),
    )

    credits_granted_count = (
        credit_summary["credit_count"] or 0
    )

    credits_amount = decimal_value(
        credit_summary["total_amount"]
    )

    # ==========================================================
    # REMBOURSEMENTS
    # ==========================================================

    repayment_operations = PretRemboursement.objects.filter(
        date_creation__range=(start_datetime, end_datetime),
    )

    validated_repayments = repayment_operations.filter(
        statut__in=repayment_success_statuses,
    )

    repayment_summary = validated_repayments.aggregate(
        repayment_count=Count("id"),
        total_amount=Sum("montant"),
    )

    repayments_count = (
        repayment_summary["repayment_count"] or 0
    )

    repayments_amount = decimal_value(
        repayment_summary["total_amount"]
    )

    # ==========================================================
    # TAUX DE RÉUSSITE DES OPÉRATIONS
    # ==========================================================

    total_transactions = (
        tontine_operations.count()
        + savings_operations.count()
        + repayment_operations.count()
    )

    successful_transactions = (
        contributions_count
        + savings_deposits_count
        + repayments_count
    )

    successful_transaction_rate = percentage(
        successful_transactions,
        total_transactions,
    )

    # ==========================================================
    # RÉSULTAT JSON-SERIALISABLE
    # ==========================================================

    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),

        # Données de la période
        "accounts_created": accounts_created,
        "active_users": active_users,
        "groups_created": groups_created,
        "registered_members": registered_members,

        # Totaux actuels
        "total_active_accounts": total_active_accounts,
        "total_groups": total_groups,
        "total_registered_members": total_registered_members,

        # Finance communautaire
        "contributions_count": contributions_count,
        "contributions_amount": float(contributions_amount),

        "savings_deposits_count": savings_deposits_count,
        "savings_amount": float(savings_amount),

        "credits_granted_count": credits_granted_count,
        "credits_amount": float(credits_amount),

        "repayments_count": repayments_count,
        "repayments_amount": float(repayments_amount),

        # Investissement non encore présent dans vos modèles
        "investments_count": dashboard.investments_count,
        "investments_amount": float(
            dashboard.investments_amount
        ),

        # Technique
        "successful_transaction_rate": (
            successful_transaction_rate
        ),

        "platform_availability": float(
            dashboard.platform_availability
        ),

        "average_response_time": float(
            dashboard.average_response_time
        ),

        "critical_incidents": dashboard.critical_incidents,

        "total_transactions": total_transactions,
        "successful_transactions": successful_transactions,

        "updated_at": timezone.localtime().strftime(
            "%d/%m/%Y à %H:%M:%S"
        ),
    }
