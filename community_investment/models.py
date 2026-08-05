from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


# ==========================================================
# CONSTANTES
# ==========================================================

ZERO_MONEY = Decimal("0.00")
ONE_CENT = Decimal("0.01")
HUNDRED_PERCENT = Decimal("100.00")

DEFAULT_INVESTMENT_THRESHOLD = Decimal("30000000.00")
DEFAULT_MINIMUM_GROUP_EQUITY_RATE = Decimal("60.00")
DEFAULT_POSTE_TARGET_RATE = Decimal("12.00")
DEFAULT_YAAYESS_TARGET_RATE = Decimal("8.00")


# ==========================================================
# FONCTIONS UTILITAIRES
# ==========================================================

def money_or_zero(value) -> Decimal:
    """
    Retourne une valeur Decimal ou zéro lorsque la valeur est nulle.
    """
    if value is None:
        return ZERO_MONEY

    return Decimal(value)


def project_document_upload_to(instance, filename: str) -> str:
    """
    Organisation des documents par projet.
    """
    return (
        "community_investment/"
        f"projects/{instance.project_id}/documents/{filename}"
    )


def contribution_document_upload_to(instance, filename: str) -> str:
    """
    Organisation des justificatifs d'apports.
    """
    return (
        "community_investment/"
        f"projects/{instance.project_id}/contributions/{filename}"
    )


# ==========================================================
# MODÈLE ABSTRAIT DE TRAÇABILITÉ
# ==========================================================

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(
        "Créé le",
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        "Mis à jour le",
        auto_now=True,
    )

    class Meta:
        abstract = True


# ==========================================================
# RÉGION POSTALE
# ==========================================================

class PostalRegion(TimeStampedModel):
    """
    Direction ou zone régionale de La Poste Sénégal.

    Elle consolide les bureaux de poste et les investissements
    communautaires d'un territoire.
    """

    name = models.CharField(
        "Nom de la région",
        max_length=150,
        unique=True,
    )

    code = models.CharField(
        "Code de la région",
        max_length=30,
        unique=True,
        help_text="Exemples : DKR, THS, KOL, STL.",
    )

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_postal_regions",
        verbose_name="Responsable régional",
    )

    description = models.TextField(
        "Description",
        blank=True,
    )

    is_active = models.BooleanField(
        "Région active",
        default=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Région postale"
        verbose_name_plural = "Régions postales"

        indexes = [
            models.Index(
                fields=["code"],
                name="ci_region_code_idx",
            ),
            models.Index(
                fields=["is_active"],
                name="ci_region_active_idx",
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


# ==========================================================
# BUREAU DE POSTE
# ==========================================================

class PostalOffice(TimeStampedModel):
    """
    Bureau de poste assurant l'accompagnement territorial
    des groupements et des projets communautaires.
    """

    region = models.ForeignKey(
        PostalRegion,
        on_delete=models.PROTECT,
        related_name="postal_offices",
        verbose_name="Région postale",
    )

    name = models.CharField(
        "Nom du bureau",
        max_length=180,
    )

    code = models.CharField(
        "Code du bureau",
        max_length=40,
        unique=True,
    )

    city = models.CharField(
        "Ville",
        max_length=120,
    )

    address = models.CharField(
        "Adresse",
        max_length=255,
        blank=True,
    )

    phone = models.CharField(
        "Téléphone",
        max_length=30,
        blank=True,
    )

    email = models.EmailField(
        "Adresse électronique",
        blank=True,
    )

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_postal_offices",
        verbose_name="Responsable du bureau",
    )

    authorized_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="authorized_postal_offices",
        verbose_name="Utilisateurs autorisés",
    )

    is_active = models.BooleanField(
        "Bureau actif",
        default=True,
    )

    class Meta:
        ordering = ["region__name", "name"]
        verbose_name = "Bureau de poste"
        verbose_name_plural = "Bureaux de poste"

        constraints = [
            models.UniqueConstraint(
                fields=["region", "name"],
                name="ci_unique_office_region",
            ),
        ]

        indexes = [
            models.Index(
                fields=["region", "is_active"],
                name="ci_office_region_idx",
            ),
            models.Index(
                fields=["code"],
                name="ci_office_code_idx",
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.city = self.city.strip()

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} — {self.region.code}"


# ==========================================================
# POLITIQUE D'ÉLIGIBILITÉ
# ==========================================================

class InvestmentEligibilityPolicy(TimeStampedModel):
    """
    Politique de maturité financière et organisationnelle permettant
    à un groupement d'accéder au programme d'investissement.

    Elle ne repose pas sur une logique de crédit ou de remboursement.
    """

    name = models.CharField(
        "Nom de la politique",
        max_length=180,
        unique=True,
        default="Politique standard d'investissement communautaire",
    )

    minimum_capital = models.DecimalField(
        "Capital collectif minimum",
        max_digits=18,
        decimal_places=2,
        default=DEFAULT_INVESTMENT_THRESHOLD,
        validators=[
            MinValueValidator(ONE_CENT),
        ],
        help_text=(
            "Seuil de capitalisation permettant au groupement "
            "d'accéder à l'accompagnement. "
            "Valeur initiale : 30 000 000 FCFA."
        ),
    )

    minimum_group_age_months = models.PositiveSmallIntegerField(
        "Ancienneté minimale du groupement en mois",
        default=12,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(240),
        ],
    )

    minimum_active_members = models.PositiveIntegerField(
        "Nombre minimal de membres actifs",
        default=10,
        validators=[
            MinValueValidator(1),
        ],
    )

    minimum_savings_regularity_rate = models.DecimalField(
        "Régularité minimale de l'épargne (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("80.00"),
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    minimum_governance_score = models.DecimalField(
        "Score minimal de gouvernance (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("70.00"),
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    minimum_internal_reserve_rate = models.DecimalField(
        "Réserve interne minimale du groupement (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    minimum_group_equity_rate = models.DecimalField(
        "Participation minimale du groupement (%)",
        max_digits=5,
        decimal_places=2,
        default=DEFAULT_MINIMUM_GROUP_EQUITY_RATE,
        validators=[
            MinValueValidator(ONE_CENT),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
        help_text=(
            "Participation économique minimale devant rester détenue "
            "par le groupement dans le projet."
        ),
    )

    suggested_poste_equity_rate = models.DecimalField(
        "Participation indicative de La Poste (%)",
        max_digits=5,
        decimal_places=2,
        default=DEFAULT_POSTE_TARGET_RATE,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
        help_text=(
            "Valeur indicative uniquement. La participation définitive "
            "doit résulter d'apports valorisés et d'une convention signée."
        ),
    )

    suggested_yaayess_equity_rate = models.DecimalField(
        "Participation indicative de YAAYESS (%)",
        max_digits=5,
        decimal_places=2,
        default=DEFAULT_YAAYESS_TARGET_RATE,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
        help_text=(
            "Valeur indicative uniquement. La participation définitive "
            "doit résulter d'apports valorisés et d'une convention signée."
        ),
    )

    requires_general_assembly_resolution = models.BooleanField(
        "Résolution de l'assemblée générale requise",
        default=True,
    )

    requires_business_plan = models.BooleanField(
        "Plan d'affaires requis",
        default=True,
    )

    requires_feasibility_study = models.BooleanField(
        "Étude de faisabilité requise",
        default=True,
    )

    requires_verified_financial_statements = models.BooleanField(
        "États financiers vérifiés requis",
        default=True,
    )

    requires_environmental_assessment = models.BooleanField(
        "Évaluation environnementale requise",
        default=False,
    )

    requires_conflict_of_interest_declaration = models.BooleanField(
        "Déclaration des conflits d'intérêts requise",
        default=True,
    )

    requires_signed_investment_agreement = models.BooleanField(
        "Convention d'investissement signée requise",
        default=True,
    )

    effective_from = models.DateField(
        "Date d'entrée en vigueur",
        default=timezone.localdate,
    )

    effective_until = models.DateField(
        "Date de fin d'application",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        "Politique active",
        default=True,
    )

    notes = models.TextField(
        "Observations",
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_investment_policies",
        verbose_name="Créée par",
    )

    class Meta:
        ordering = ["-is_active", "-effective_from"]
        verbose_name = "Politique d'éligibilité"
        verbose_name_plural = "Politiques d'éligibilité"

        constraints = [
            models.CheckConstraint(
                condition=Q(minimum_capital__gt=0),
                name="ci_policy_capital_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(minimum_group_equity_rate__gt=0)
                    & Q(minimum_group_equity_rate__lte=100)
                ),
                name="ci_policy_group_equity",
            ),
            models.CheckConstraint(
                condition=(
                    Q(minimum_governance_score__gte=0)
                    & Q(minimum_governance_score__lte=100)
                ),
                name="ci_policy_governance",
            ),
            models.UniqueConstraint(
                fields=["is_active"],
                condition=Q(is_active=True),
                name="ci_only_one_active_policy",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if (
            self.effective_until
            and self.effective_until < self.effective_from
        ):
            errors["effective_until"] = (
                "La date de fin doit être postérieure "
                "à la date d'entrée en vigueur."
            )

        total_indicative_rate = (
            self.minimum_group_equity_rate
            + self.suggested_poste_equity_rate
            + self.suggested_yaayess_equity_rate
        )

        if total_indicative_rate > HUNDRED_PERCENT:
            errors["suggested_yaayess_equity_rate"] = (
                "La participation minimale du groupement et les "
                "participations indicatives de La Poste et de YAAYESS "
                "ne peuvent pas dépasser 100 %."
            )

        if errors:
            raise ValidationError(errors)

    @classmethod
    def get_active_policy(
        cls,
    ) -> InvestmentEligibilityPolicy | None:
        today = timezone.localdate()

        return (
            cls.objects
            .filter(
                is_active=True,
                effective_from__lte=today,
            )
            .filter(
                Q(effective_until__isnull=True)
                | Q(effective_until__gte=today)
            )
            .first()
        )

    def __str__(self) -> str:
        amount = f"{self.minimum_capital:,.0f}".replace(",", " ")

        return f"{self.name} — seuil {amount} FCFA"


# ==========================================================
# PROJET D'INVESTISSEMENT COMMUNAUTAIRE
# ==========================================================

class CommunityInvestmentProject(TimeStampedModel):
    """
    Projet productif financé par le capital collectif d'un groupement.

    La Poste, YAAYESS et les autres partenaires peuvent participer
    au capital uniquement après valorisation et validation de leurs
    apports.
    """

    class Sector(models.TextChoices):
        AGRICULTURE = "AGRICULTURE", "Agriculture"
        LIVESTOCK = "LIVESTOCK", "Élevage"
        FISHING = "FISHING", "Pêche et aquaculture"
        TRADE = "TRADE", "Commerce"
        CRAFTS = "CRAFTS", "Artisanat"
        INDUSTRY = "INDUSTRY", "Transformation et industrie"
        REAL_ESTATE = "REAL_ESTATE", "Immobilier"
        ENERGY = "ENERGY", "Énergie"
        TRANSPORT = "TRANSPORT", "Transport et logistique"
        DIGITAL = "DIGITAL", "Numérique"
        TOURISM = "TOURISM", "Tourisme"
        HEALTH = "HEALTH", "Santé"
        EDUCATION = "EDUCATION", "Éducation et formation"
        ENVIRONMENT = "ENVIRONMENT", "Environnement"
        OTHER = "OTHER", "Autre"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SUBMITTED = "SUBMITTED", "Soumis au bureau de poste"
        OFFICE_REVIEW = "OFFICE_REVIEW", "Examen par le bureau"
        ADDITIONAL_INFO = (
            "ADDITIONAL_INFO",
            "Informations complémentaires requises",
        )
        REGIONAL_REVIEW = "REGIONAL_REVIEW", "Examen régional"
        CENTRAL_REVIEW = (
            "CENTRAL_REVIEW",
            "Instruction par la Direction des investissements",
        )
        ELIGIBLE = "ELIGIBLE", "Éligible"
        NOT_ELIGIBLE = "NOT_ELIGIBLE", "Non éligible"
        STRUCTURING = "STRUCTURING", "Structuration"
        APPROVED = "APPROVED", "Approuvé"
        REJECTED = "REJECTED", "Rejeté"
        CAPITALIZATION = "CAPITALIZATION", "Capital en constitution"
        READY_TO_START = "READY_TO_START", "Prêt à démarrer"
        IN_PROGRESS = "IN_PROGRESS", "En exploitation"
        SUSPENDED = "SUSPENDED", "Suspendu"
        COMPLETED = "COMPLETED", "Cycle terminé"
        CLOSED = "CLOSED", "Clôturé"
        CANCELLED = "CANCELLED", "Annulé"

    class RiskLevel(models.TextChoices):
        LOW = "LOW", "Faible"
        MODERATE = "MODERATE", "Modéré"
        HIGH = "HIGH", "Élevé"
        CRITICAL = "CRITICAL", "Critique"

    class EligibilityStatus(models.TextChoices):
        PENDING = "PENDING", "À évaluer"
        ELIGIBLE = "ELIGIBLE", "Éligible"
        NOT_ELIGIBLE = "NOT_ELIGIBLE", "Non éligible"
        OVERRIDDEN = "OVERRIDDEN", "Dérogation approuvée"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    reference = models.CharField(
        "Référence",
        max_length=40,
        unique=True,
        editable=False,
    )

    group = models.ForeignKey(
        "epargnecredit.Group",
        on_delete=models.PROTECT,
        related_name="community_investment_projects",
        verbose_name="Groupement d'épargne-crédit",
    )

    postal_office = models.ForeignKey(
        PostalOffice,
        on_delete=models.PROTECT,
        related_name="community_investment_projects",
        verbose_name="Bureau de poste accompagnateur",
    )

    eligibility_policy = models.ForeignKey(
        InvestmentEligibilityPolicy,
        on_delete=models.PROTECT,
        related_name="projects",
        verbose_name="Politique d'éligibilité appliquée",
    )

    title = models.CharField(
        "Titre du projet",
        max_length=255,
    )

    description = models.TextField(
        "Description du projet",
    )

    sector = models.CharField(
        "Secteur d'activité",
        max_length=30,
        choices=Sector.choices,
    )

    project_location = models.CharField(
        "Localisation du projet",
        max_length=255,
        blank=True,
    )

    project_lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="led_community_investment_projects",
        verbose_name="Responsable opérationnel",
    )

    capital_at_submission = models.DecimalField(
        "Capital du groupement à la soumission",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    threshold_at_submission = models.DecimalField(
        "Seuil applicable à la soumission",
        max_digits=18,
        decimal_places=2,
        default=DEFAULT_INVESTMENT_THRESHOLD,
        validators=[
            MinValueValidator(ONE_CENT),
        ],
        editable=False,
    )

    total_project_cost = models.DecimalField(
        "Coût total estimé du projet",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    group_planned_equity = models.DecimalField(
        "Participation prévue du groupement",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    expected_return_rate = models.DecimalField(
        "Rendement annuel attendu (%)",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    expected_jobs = models.PositiveIntegerField(
        "Nombre d'emplois prévus",
        default=0,
    )

    expected_beneficiaries = models.PositiveIntegerField(
        "Nombre de bénéficiaires prévus",
        default=0,
    )

    governance_score = models.DecimalField(
        "Score de gouvernance (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    savings_regularity_rate = models.DecimalField(
        "Régularité de l'épargne (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    status = models.CharField(
        "Statut",
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    eligibility_status = models.CharField(
        "Statut d'éligibilité",
        max_length=20,
        choices=EligibilityStatus.choices,
        default=EligibilityStatus.PENDING,
    )

    risk_level = models.CharField(
        "Niveau de risque",
        max_length=20,
        choices=RiskLevel.choices,
        default=RiskLevel.MODERATE,
    )

    progress_percentage = models.DecimalField(
        "Avancement opérationnel (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    general_assembly_resolution_reference = models.CharField(
        "Référence de la résolution du groupement",
        max_length=120,
        blank=True,
    )

    general_assembly_resolution_date = models.DateField(
        "Date de la résolution",
        null=True,
        blank=True,
    )

    planned_start_date = models.DateField(
        "Date de démarrage prévue",
        null=True,
        blank=True,
    )

    planned_end_date = models.DateField(
        "Date de fin prévue",
        null=True,
        blank=True,
    )

    actual_start_date = models.DateField(
        "Date de démarrage réelle",
        null=True,
        blank=True,
    )

    actual_end_date = models.DateField(
        "Date de fin réelle",
        null=True,
        blank=True,
    )

    submitted_at = models.DateTimeField(
        "Soumis le",
        null=True,
        blank=True,
    )

    reviewed_at = models.DateTimeField(
        "Examiné le",
        null=True,
        blank=True,
    )

    decided_at = models.DateTimeField(
        "Décision prise le",
        null=True,
        blank=True,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_community_investment_projects",
        verbose_name="Examiné par",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_community_investment_projects",
        verbose_name="Approuvé par",
    )

    eligibility_override_reason = models.TextField(
        "Motif de dérogation",
        blank=True,
    )

    rejection_reason = models.TextField(
        "Motif du rejet",
        blank=True,
    )

    internal_notes = models.TextField(
        "Notes internes",
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_community_investment_projects",
        verbose_name="Créé par",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Projet d'investissement communautaire"
        verbose_name_plural = "Projets d'investissement communautaire"

        permissions = [
            (
                "manage_community_investments",
                "Peut gérer les investissements communautaires",
            ),
            (
                "review_community_investment",
                "Peut instruire un investissement communautaire",
            ),
            (
                "approve_community_investment",
                "Peut approuver un investissement communautaire",
            ),
            (
                "view_national_investment_dashboard",
                "Peut consulter le tableau de bord national",
            ),
            (
                "view_project_financial_data",
                "Peut consulter les données financières des projets",
            ),
            (
                "validate_project_contribution",
                "Peut valider les apports aux projets",
            ),
            (
                "approve_profit_allocation",
                "Peut approuver l'affectation des bénéfices",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(total_project_cost__gte=0),
                name="ci_project_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(group_planned_equity__gte=0),
                name="ci_project_group_equity",
            ),
            models.CheckConstraint(
                condition=(
                    Q(progress_percentage__gte=0)
                    & Q(progress_percentage__lte=100)
                ),
                name="ci_project_progress_valid",
            ),
        ]

        indexes = [
            models.Index(
                fields=["status", "risk_level"],
                name="ci_project_status_risk_idx",
            ),
            models.Index(
                fields=["postal_office", "status"],
                name="ci_project_office_status_idx",
            ),
            models.Index(
                fields=["group", "status"],
                name="ci_project_group_status_idx",
            ),
            models.Index(
                fields=["eligibility_status"],
                name="ci_project_eligibility_idx",
            ),
            models.Index(
                fields=["created_at"],
                name="ci_project_created_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if self.total_project_cost <= ZERO_MONEY:
            errors["total_project_cost"] = (
                "Le coût total estimé du projet doit être supérieur à zéro."
            )

        if self.group_planned_equity > self.total_project_cost:
            errors["group_planned_equity"] = (
                "La participation prévue du groupement ne peut pas "
                "dépasser le coût total du projet."
            )

        if (
            self.planned_start_date
            and self.planned_end_date
            and self.planned_end_date < self.planned_start_date
        ):
            errors["planned_end_date"] = (
                "La date de fin prévue doit être postérieure "
                "à la date de démarrage prévue."
            )

        if (
            self.actual_start_date
            and self.actual_end_date
            and self.actual_end_date < self.actual_start_date
        ):
            errors["actual_end_date"] = (
                "La date de fin réelle doit être postérieure "
                "à la date de démarrage réelle."
            )

        if (
            self.eligibility_status
            == self.EligibilityStatus.OVERRIDDEN
            and not self.eligibility_override_reason.strip()
        ):
            errors["eligibility_override_reason"] = (
                "Le motif de la dérogation est obligatoire."
            )

        if (
            self.status == self.Status.REJECTED
            and not self.rejection_reason.strip()
        ):
            errors["rejection_reason"] = (
                "Le motif du rejet est obligatoire."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def is_capital_threshold_reached(self) -> bool:
        return self.capital_at_submission >= self.threshold_at_submission

    @property
    def total_recognized_capital(self) -> Decimal:
        result = self.contributions.filter(
            status=ProjectContribution.Status.RECOGNIZED,
        ).aggregate(
            total=Sum("recognized_value"),
        )

        return money_or_zero(result["total"])

    @property
    def remaining_capital_to_raise(self) -> Decimal:
        remaining = (
            self.total_project_cost
            - self.total_recognized_capital
        )

        return max(remaining, ZERO_MONEY)

    @property
    def capital_completion_rate(self) -> Decimal:
        if self.total_project_cost <= ZERO_MONEY:
            return ZERO_MONEY

        rate = (
            self.total_recognized_capital
            / self.total_project_cost
            * HUNDRED_PERCENT
        )

        return min(rate, HUNDRED_PERCENT)

    @property
    def total_active_ownership_percentage(self) -> Decimal:
        result = self.stakeholders.filter(
            status=ProjectStakeholder.Status.ACTIVE,
        ).aggregate(
            total=Sum("ownership_percentage"),
        )

        return money_or_zero(result["total"])

    def evaluate_basic_eligibility(self) -> bool:
        policy = self.eligibility_policy

        is_eligible = all(
            [
                self.capital_at_submission >= policy.minimum_capital,
                self.governance_score >= policy.minimum_governance_score,
                (
                    self.savings_regularity_rate
                    >= policy.minimum_savings_regularity_rate
                ),
            ]
        )

        self.eligibility_status = (
            self.EligibilityStatus.ELIGIBLE
            if is_eligible
            else self.EligibilityStatus.NOT_ELIGIBLE
        )

        return is_eligible

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding

        if not self.reference:
            self.reference = (
                f"YCI-{timezone.now():%Y%m%d}-"
                f"{uuid.uuid4().hex[:8].upper()}"
            )

        if self.eligibility_policy_id and is_new:
            self.threshold_at_submission = (
                self.eligibility_policy.minimum_capital
            )

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.reference} — {self.title}"


# ==========================================================
# ENTITÉ JURIDIQUE PORTEUSE
# ==========================================================

class ProjectLegalEntity(TimeStampedModel):
    class LegalForm(models.TextChoices):
        COOPERATIVE = "COOPERATIVE", "Société coopérative"
        SARL = "SARL", "SARL"
        SAS = "SAS", "SAS"
        SA = "SA", "SA"
        GIE = "GIE", "GIE"
        ASSOCIATION = "ASSOCIATION", "Association"
        OTHER = "OTHER", "Autre"

    project = models.OneToOneField(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="legal_entity",
        verbose_name="Projet",
    )

    legal_name = models.CharField(
        "Dénomination sociale",
        max_length=255,
    )

    legal_form = models.CharField(
        "Forme juridique",
        max_length=30,
        choices=LegalForm.choices,
    )

    registration_number = models.CharField(
        "Numéro d'immatriculation",
        max_length=120,
        blank=True,
    )

    tax_number = models.CharField(
        "Identifiant fiscal",
        max_length=120,
        blank=True,
    )

    registered_office = models.CharField(
        "Siège social",
        max_length=255,
        blank=True,
    )

    share_capital = models.DecimalField(
        "Capital social",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    incorporation_date = models.DateField(
        "Date de constitution",
        null=True,
        blank=True,
    )

    is_registered = models.BooleanField(
        "Entité immatriculée",
        default=False,
    )

    def __str__(self) -> str:
        return self.legal_name


# ==========================================================
# ASSOCIÉS ET ACTIONNAIRES
# ==========================================================

class ProjectStakeholder(TimeStampedModel):
    class HolderType(models.TextChoices):
        GROUP = "GROUP", "Groupement"
        POSTE = "POSTE", "La Poste Sénégal"
        YAAYESS = "YAAYESS", "YAAYESS"
        PARTNER = "PARTNER", "Partenaire institutionnel"
        INDIVIDUAL = "INDIVIDUAL", "Personne physique"
        OTHER = "OTHER", "Autre"

    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Proposé"
        APPROVED = "APPROVED", "Approuvé"
        ACTIVE = "ACTIVE", "Participation active"
        SUSPENDED = "SUSPENDED", "Suspendu"
        EXITED = "EXITED", "Sorti du capital"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="stakeholders",
        verbose_name="Projet",
    )

    holder_type = models.CharField(
        "Type d'associé ou d'actionnaire",
        max_length=20,
        choices=HolderType.choices,
    )

    group = models.ForeignKey(
        "epargnecredit.Group",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="investment_stakeholdings",
        verbose_name="Groupement",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="investment_stakeholdings",
        verbose_name="Personne physique",
    )

    legal_name = models.CharField(
        "Nom ou dénomination",
        max_length=255,
        blank=True,
    )

    shares_count = models.PositiveBigIntegerField(
        "Nombre de parts ou actions",
        default=0,
    )

    ownership_percentage = models.DecimalField(
        "Participation économique (%)",
        max_digits=7,
        decimal_places=4,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    voting_percentage = models.DecimalField(
        "Droits de vote (%)",
        max_digits=7,
        decimal_places=4,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.PROPOSED,
    )

    investment_agreement_reference = models.CharField(
        "Référence de la convention d'investissement",
        max_length=120,
        blank=True,
    )

    approved_at = models.DateTimeField(
        "Participation approuvée le",
        null=True,
        blank=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_project_stakeholders",
        verbose_name="Approuvée par",
    )

    notes = models.TextField(
        "Observations",
        blank=True,
    )

    class Meta:
        ordering = ["project", "-ownership_percentage"]
        verbose_name = "Associé ou actionnaire"
        verbose_name_plural = "Associés et actionnaires"

        constraints = [
            models.UniqueConstraint(
                fields=["project", "holder_type"],
                condition=Q(
                    holder_type__in=[
                        "GROUP",
                        "POSTE",
                        "YAAYESS",
                    ]
                ),
                name="ci_unique_core_holder",
            ),
            models.CheckConstraint(
                condition=(
                    Q(ownership_percentage__gte=0)
                    & Q(ownership_percentage__lte=100)
                ),
                name="ci_holder_ownership_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(voting_percentage__gte=0)
                    & Q(voting_percentage__lte=100)
                ),
                name="ci_holder_voting_valid",
            ),
        ]

        indexes = [
            models.Index(
                fields=["project", "holder_type", "status"],
                name="ci_holder_project_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if self.holder_type == self.HolderType.GROUP:
            if not self.group_id:
                errors["group"] = "Le groupement est obligatoire."

            elif self.project_id and self.group_id != self.project.group_id:
                errors["group"] = (
                    "Le groupement actionnaire doit être le groupement "
                    "porteur du projet."
                )

        if (
            self.holder_type == self.HolderType.INDIVIDUAL
            and not self.user_id
        ):
            errors["user"] = (
                "La personne physique est obligatoire."
            )

        if self.holder_type in {
            self.HolderType.PARTNER,
            self.HolderType.OTHER,
        } and not self.legal_name.strip():
            errors["legal_name"] = (
                "La dénomination du partenaire est obligatoire."
            )

        if (
            self.status in {
                self.Status.APPROVED,
                self.Status.ACTIVE,
            }
            and not self.investment_agreement_reference.strip()
        ):
            errors["investment_agreement_reference"] = (
                "La référence de la convention d'investissement "
                "est obligatoire avant l'approbation."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if self.holder_type == self.HolderType.POSTE:
            self.legal_name = "La Poste Sénégal"

        elif self.holder_type == self.HolderType.YAAYESS:
            self.legal_name = "YAAYESS — Systèmes & Technologie"

        elif (
            self.holder_type == self.HolderType.GROUP
            and self.group_id
        ):
            self.legal_name = self.group.nom

        elif (
            self.holder_type == self.HolderType.INDIVIDUAL
            and self.user_id
        ):
            self.legal_name = (
                self.user.nom
                or self.user.phone
            )

        super().save(*args, **kwargs)

    @property
    def recognized_contribution_value(self) -> Decimal:
        result = self.contributions.filter(
            status=ProjectContribution.Status.RECOGNIZED,
        ).aggregate(
            total=Sum("recognized_value"),
        )

        return money_or_zero(result["total"])

    def __str__(self) -> str:
        return (
            f"{self.legal_name} — "
            f"{self.ownership_percentage}%"
        )


# ==========================================================
# APPORTS AUX PROJETS
# ==========================================================

class ProjectContribution(TimeStampedModel):
    class ContributionType(models.TextChoices):
        CASH = "CASH", "Apport financier"
        LAND = "LAND", "Terrain"
        BUILDING = "BUILDING", "Bâtiment"
        EQUIPMENT = "EQUIPMENT", "Équipement"
        TECHNOLOGY = "TECHNOLOGY", "Technologie"
        SOFTWARE = "SOFTWARE", "Plateforme ou logiciel"
        INTELLECTUAL_PROPERTY = (
            "INTELLECTUAL_PROPERTY",
            "Propriété intellectuelle",
        )
        NETWORK = "NETWORK", "Réseau territorial ou commercial"
        MANAGEMENT = "MANAGEMENT", "Accompagnement et gestion"
        EXPERTISE = "EXPERTISE", "Expertise technique"
        OTHER = "OTHER", "Autre apport"

    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Proposé"
        UNDER_VALUATION = "UNDER_VALUATION", "En évaluation"
        RECOGNIZED = "RECOGNIZED", "Apport reconnu"
        REJECTED = "REJECTED", "Apport rejeté"
        CANCELLED = "CANCELLED", "Apport annulé"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="contributions",
        verbose_name="Projet",
    )

    stakeholder = models.ForeignKey(
        ProjectStakeholder,
        on_delete=models.CASCADE,
        related_name="contributions",
        verbose_name="Associé ou actionnaire",
    )

    contribution_type = models.CharField(
        "Nature de l'apport",
        max_length=30,
        choices=ContributionType.choices,
    )

    description = models.TextField(
        "Description de l'apport",
    )

    declared_value = models.DecimalField(
        "Valeur déclarée",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    recognized_value = models.DecimalField(
        "Valeur reconnue",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    valuation_method = models.CharField(
        "Méthode de valorisation",
        max_length=255,
        blank=True,
    )

    valuation_report_reference = models.CharField(
        "Référence du rapport de valorisation",
        max_length=120,
        blank=True,
    )

    supporting_document = models.FileField(
        "Document justificatif",
        upload_to=contribution_document_upload_to,
        blank=True,
    )

    status = models.CharField(
        "Statut",
        max_length=25,
        choices=Status.choices,
        default=Status.PROPOSED,
    )

    contribution_date = models.DateField(
        "Date de l'apport",
        null=True,
        blank=True,
    )

    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_project_contributions",
        verbose_name="Validé par",
    )

    validated_at = models.DateTimeField(
        "Validé le",
        null=True,
        blank=True,
    )

    notes = models.TextField(
        "Observations",
        blank=True,
    )

    class Meta:
        ordering = ["project", "stakeholder", "created_at"]
        verbose_name = "Apport au projet"
        verbose_name_plural = "Apports aux projets"

        constraints = [
            models.CheckConstraint(
                condition=Q(declared_value__gte=0),
                name="ci_contribution_declared",
            ),
            models.CheckConstraint(
                condition=Q(recognized_value__gte=0),
                name="ci_contribution_recognized",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if (
            self.stakeholder_id
            and self.project_id
            and self.stakeholder.project_id != self.project_id
        ):
            errors["stakeholder"] = (
                "L'associé ou actionnaire doit appartenir "
                "au même projet."
            )

        if (
            self.status == self.Status.RECOGNIZED
            and self.recognized_value <= ZERO_MONEY
        ):
            errors["recognized_value"] = (
                "La valeur reconnue doit être supérieure à zéro."
            )

        if (
            self.status == self.Status.RECOGNIZED
            and not self.valuation_method.strip()
        ):
            errors["valuation_method"] = (
                "La méthode de valorisation est obligatoire."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return (
            f"{self.get_contribution_type_display()} — "
            f"{self.stakeholder.legal_name}"
        )


# ==========================================================
# DROITS ÉCONOMIQUES DES MEMBRES
# ==========================================================

class MemberEconomicRight(TimeStampedModel):
    """
    Le groupement reste l'actionnaire juridique.

    Chaque membre conserve toutefois une quote-part économique
    interne dans la participation du groupement.
    """

    stakeholder = models.ForeignKey(
        ProjectStakeholder,
        on_delete=models.CASCADE,
        related_name="member_economic_rights",
        verbose_name="Participation du groupement",
    )

    member = models.ForeignKey(
        "epargnecredit.GroupMember",
        on_delete=models.PROTECT,
        related_name="investment_economic_rights",
        verbose_name="Membre du groupement",
    )

    contribution_reference_amount = models.DecimalField(
        "Contribution de référence",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    economic_percentage = models.DecimalField(
        "Quote-part économique interne (%)",
        max_digits=7,
        decimal_places=4,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    dividend_percentage = models.DecimalField(
        "Droit interne aux dividendes (%)",
        max_digits=7,
        decimal_places=4,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    is_active = models.BooleanField(
        "Droit actif",
        default=True,
    )

    effective_from = models.DateField(
        "Applicable à partir du",
        default=timezone.localdate,
    )

    effective_until = models.DateField(
        "Applicable jusqu'au",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Droit économique d'un membre"
        verbose_name_plural = "Droits économiques des membres"

        constraints = [
            models.UniqueConstraint(
                fields=["stakeholder", "member"],
                name="ci_unique_member_right",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if (
            self.stakeholder_id
            and self.stakeholder.holder_type
            != ProjectStakeholder.HolderType.GROUP
        ):
            errors["stakeholder"] = (
                "Les droits internes doivent être rattachés "
                "à une participation de type groupement."
            )

        if (
            self.stakeholder_id
            and self.member_id
            and self.stakeholder.group_id != self.member.group_id
        ):
            errors["member"] = (
                "Le membre doit appartenir au groupement actionnaire."
            )

        if (
            self.effective_until
            and self.effective_until < self.effective_from
        ):
            errors["effective_until"] = (
                "La date de fin doit être postérieure "
                "à la date de début."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return (
            f"{self.member} — "
            f"{self.economic_percentage}%"
        )


# ==========================================================
# MOUVEMENTS DE PARTS OU ACTIONS
# ==========================================================

class ShareTransaction(TimeStampedModel):
    class TransactionType(models.TextChoices):
        INITIAL_SUBSCRIPTION = (
            "INITIAL_SUBSCRIPTION",
            "Souscription initiale",
        )
        CAPITAL_INCREASE = (
            "CAPITAL_INCREASE",
            "Augmentation de capital",
        )
        TRANSFER = "TRANSFER", "Transfert"
        REDEMPTION = "REDEMPTION", "Rachat"
        CANCELLATION = "CANCELLATION", "Annulation"
        ADJUSTMENT = "ADJUSTMENT", "Régularisation"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="share_transactions",
        verbose_name="Projet",
    )

    transaction_type = models.CharField(
        "Type d'opération",
        max_length=30,
        choices=TransactionType.choices,
    )

    from_stakeholder = models.ForeignKey(
        ProjectStakeholder,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="outgoing_share_transactions",
        verbose_name="Cédant",
    )

    to_stakeholder = models.ForeignKey(
        ProjectStakeholder,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_share_transactions",
        verbose_name="Bénéficiaire",
    )

    shares_count = models.PositiveBigIntegerField(
        "Nombre de titres",
        default=0,
    )

    transaction_amount = models.DecimalField(
        "Montant",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    transaction_date = models.DateField(
        "Date de l'opération",
        default=timezone.localdate,
    )

    resolution_reference = models.CharField(
        "Référence de la décision",
        max_length=120,
        blank=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_share_transactions",
        verbose_name="Approuvé par",
    )

    notes = models.TextField(
        "Observations",
        blank=True,
    )

    class Meta:
        ordering = ["-transaction_date", "-created_at"]
        verbose_name = "Mouvement de parts ou actions"
        verbose_name_plural = "Mouvements de parts ou actions"

    def clean(self) -> None:
        super().clean()

        errors = {}

        for field_name in (
            "from_stakeholder",
            "to_stakeholder",
        ):
            stakeholder = getattr(self, field_name)

            if (
                stakeholder
                and stakeholder.project_id != self.project_id
            ):
                errors[field_name] = (
                    "L'associé ou actionnaire doit appartenir "
                    "au même projet."
                )

        if (
            self.from_stakeholder_id
            and self.to_stakeholder_id
            and self.from_stakeholder_id == self.to_stakeholder_id
        ):
            errors["to_stakeholder"] = (
                "Le cédant et le bénéficiaire doivent être différents."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return (
            f"{self.get_transaction_type_display()} — "
            f"{self.project.reference}"
        )


# ==========================================================
# MODÈLE ÉCONOMIQUE : FRAIS DE LA POSTE ET DE YAAYESS
# ==========================================================

class ProjectFeeRule(TimeStampedModel):
    """
    Règle de rémunération contractuelle de La Poste, de YAAYESS
    ou d'un partenaire.

    Cette rémunération est distincte de l'actionnariat et des dividendes.
    """

    class BeneficiaryType(models.TextChoices):
        POSTE = "POSTE", "La Poste Sénégal"
        YAAYESS = "YAAYESS", "YAAYESS"
        PARTNER = "PARTNER", "Partenaire"
        PROJECT_DIRECTION = (
            "PROJECT_DIRECTION",
            "Direction des investissements communautaires",
        )

    class FeeType(models.TextChoices):
        STRUCTURING = "STRUCTURING", "Frais de structuration"
        MANAGEMENT = "MANAGEMENT", "Frais de gestion"
        TECHNOLOGY = "TECHNOLOGY", "Frais technologiques"
        MONITORING = "MONITORING", "Frais de suivi territorial"
        PERFORMANCE = "PERFORMANCE", "Rémunération de performance"
        TRANSACTION = "TRANSACTION", "Frais de transaction"
        OTHER = "OTHER", "Autre"

    class CalculationMethod(models.TextChoices):
        FIXED = "FIXED", "Montant fixe"
        REVENUE_PERCENTAGE = (
            "REVENUE_PERCENTAGE",
            "Pourcentage du chiffre d'affaires",
        )
        PROFIT_PERCENTAGE = (
            "PROFIT_PERCENTAGE",
            "Pourcentage du bénéfice",
        )
        CAPITAL_PERCENTAGE = (
            "CAPITAL_PERCENTAGE",
            "Pourcentage du capital",
        )

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        APPROVED = "APPROVED", "Approuvée"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspendue"
        TERMINATED = "TERMINATED", "Terminée"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="fee_rules",
        verbose_name="Projet",
    )

    beneficiary_type = models.CharField(
        "Bénéficiaire",
        max_length=30,
        choices=BeneficiaryType.choices,
    )

    beneficiary_name = models.CharField(
        "Nom du bénéficiaire",
        max_length=255,
        blank=True,
    )

    fee_type = models.CharField(
        "Type de rémunération",
        max_length=30,
        choices=FeeType.choices,
    )

    calculation_method = models.CharField(
        "Mode de calcul",
        max_length=30,
        choices=CalculationMethod.choices,
    )

    fixed_amount = models.DecimalField(
        "Montant fixe",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    percentage_rate = models.DecimalField(
        "Taux (%)",
        max_digits=7,
        decimal_places=4,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    annual_cap = models.DecimalField(
        "Plafond annuel",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    effective_from = models.DateField(
        "Applicable à partir du",
        default=timezone.localdate,
    )

    effective_until = models.DateField(
        "Applicable jusqu'au",
        null=True,
        blank=True,
    )

    agreement_reference = models.CharField(
        "Référence de la convention",
        max_length=120,
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_project_fee_rules",
        verbose_name="Approuvée par",
    )

    notes = models.TextField(
        "Observations",
        blank=True,
    )

    class Meta:
        ordering = ["project", "beneficiary_type", "fee_type"]
        verbose_name = "Règle de rémunération"
        verbose_name_plural = "Règles de rémunération"

    def clean(self) -> None:
        super().clean()

        errors = {}

        if (
            self.calculation_method
            == self.CalculationMethod.FIXED
            and self.fixed_amount <= ZERO_MONEY
        ):
            errors["fixed_amount"] = (
                "Le montant fixe doit être supérieur à zéro."
            )

        if (
            self.calculation_method
            != self.CalculationMethod.FIXED
            and self.percentage_rate <= ZERO_MONEY
        ):
            errors["percentage_rate"] = (
                "Le taux doit être supérieur à zéro."
            )

        if (
            self.effective_until
            and self.effective_until < self.effective_from
        ):
            errors["effective_until"] = (
                "La date de fin doit être postérieure "
                "à la date de début."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if self.beneficiary_type == self.BeneficiaryType.POSTE:
            self.beneficiary_name = "La Poste Sénégal"

        elif self.beneficiary_type == self.BeneficiaryType.YAAYESS:
            self.beneficiary_name = (
                "YAAYESS — Systèmes & Technologie"
            )

        super().save(*args, **kwargs)

    def calculate_amount(
        self,
        *,
        revenue: Decimal = ZERO_MONEY,
        profit: Decimal = ZERO_MONEY,
        capital: Decimal = ZERO_MONEY,
    ) -> Decimal:
        if (
            self.calculation_method
            == self.CalculationMethod.FIXED
        ):
            amount = self.fixed_amount

        elif (
            self.calculation_method
            == self.CalculationMethod.REVENUE_PERCENTAGE
        ):
            amount = (
                revenue
                * self.percentage_rate
                / HUNDRED_PERCENT
            )

        elif (
            self.calculation_method
            == self.CalculationMethod.PROFIT_PERCENTAGE
        ):
            amount = (
                max(profit, ZERO_MONEY)
                * self.percentage_rate
                / HUNDRED_PERCENT
            )

        else:
            amount = (
                capital
                * self.percentage_rate
                / HUNDRED_PERCENT
            )

        if self.annual_cap is not None:
            amount = min(amount, self.annual_cap)

        return amount.quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return (
            f"{self.get_beneficiary_type_display()} — "
            f"{self.get_fee_type_display()}"
        )


class ProjectFeeAccrual(TimeStampedModel):
    """
    Montant effectivement calculé pour une règle de rémunération.
    """

    class Status(models.TextChoices):
        CALCULATED = "CALCULATED", "Calculé"
        APPROVED = "APPROVED", "Approuvé"
        PAID = "PAID", "Payé"
        CANCELLED = "CANCELLED", "Annulé"

    fee_rule = models.ForeignKey(
        ProjectFeeRule,
        on_delete=models.PROTECT,
        related_name="accruals",
        verbose_name="Règle de rémunération",
    )

    period_start = models.DateField(
        "Début de période",
    )

    period_end = models.DateField(
        "Fin de période",
    )

    calculation_base = models.DecimalField(
        "Base de calcul",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    calculated_amount = models.DecimalField(
        "Montant calculé",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.CALCULATED,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_project_fee_accruals",
        verbose_name="Approuvé par",
    )

    payment_reference = models.CharField(
        "Référence de paiement",
        max_length=150,
        blank=True,
    )

    paid_at = models.DateTimeField(
        "Payé le",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-period_end"]
        verbose_name = "Rémunération calculée"
        verbose_name_plural = "Rémunérations calculées"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "fee_rule",
                    "period_start",
                    "period_end",
                ],
                name="ci_unique_fee_period",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        if self.period_end < self.period_start:
            raise ValidationError(
                {
                    "period_end": (
                        "La date de fin doit être postérieure "
                        "à la date de début."
                    )
                }
            )

    def __str__(self) -> str:
        return (
            f"{self.fee_rule} — "
            f"{self.calculated_amount} FCFA"
        )


# ==========================================================
# REVENUS ET CHARGES
# ==========================================================

class ProjectRevenue(TimeStampedModel):
    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="revenues",
        verbose_name="Projet",
    )

    reference = models.CharField(
        "Référence",
        max_length=100,
        blank=True,
    )

    description = models.CharField(
        "Description",
        max_length=255,
    )

    amount = models.DecimalField(
        "Montant",
        max_digits=18,
        decimal_places=2,
        validators=[
            MinValueValidator(ONE_CENT),
        ],
    )

    revenue_date = models.DateField(
        "Date du revenu",
        default=timezone.localdate,
    )

    supporting_document = models.FileField(
        "Justificatif",
        upload_to=project_document_upload_to,
        blank=True,
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_project_revenues",
        verbose_name="Enregistré par",
    )

    class Meta:
        ordering = ["-revenue_date"]
        verbose_name = "Revenu du projet"
        verbose_name_plural = "Revenus des projets"

    def __str__(self) -> str:
        return f"{self.description} — {self.amount} FCFA"


class ProjectExpense(TimeStampedModel):
    class ExpenseCategory(models.TextChoices):
        RAW_MATERIALS = "RAW_MATERIALS", "Matières premières"
        SALARIES = "SALARIES", "Salaires"
        EQUIPMENT = "EQUIPMENT", "Équipements"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        TRANSPORT = "TRANSPORT", "Transport"
        ENERGY = "ENERGY", "Énergie"
        TAXES = "TAXES", "Impôts et taxes"
        MANAGEMENT = "MANAGEMENT", "Frais de gestion"
        TECHNOLOGY = "TECHNOLOGY", "Frais technologiques"
        MARKETING = "MARKETING", "Marketing"
        OTHER = "OTHER", "Autre"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="expenses",
        verbose_name="Projet",
    )

    category = models.CharField(
        "Catégorie",
        max_length=30,
        choices=ExpenseCategory.choices,
    )

    reference = models.CharField(
        "Référence",
        max_length=100,
        blank=True,
    )

    description = models.CharField(
        "Description",
        max_length=255,
    )

    amount = models.DecimalField(
        "Montant",
        max_digits=18,
        decimal_places=2,
        validators=[
            MinValueValidator(ONE_CENT),
        ],
    )

    expense_date = models.DateField(
        "Date de la charge",
        default=timezone.localdate,
    )

    supporting_document = models.FileField(
        "Justificatif",
        upload_to=project_document_upload_to,
        blank=True,
    )

    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_project_expenses",
        verbose_name="Validé par",
    )

    class Meta:
        ordering = ["-expense_date"]
        verbose_name = "Charge du projet"
        verbose_name_plural = "Charges des projets"

    def __str__(self) -> str:
        return f"{self.description} — {self.amount} FCFA"


# ==========================================================
# ÉTATS FINANCIERS
# ==========================================================

class ProjectFinancialStatement(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SUBMITTED = "SUBMITTED", "Soumis"
        VERIFIED = "VERIFIED", "Vérifié"
        APPROVED = "APPROVED", "Approuvé"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="financial_statements",
        verbose_name="Projet",
    )

    period_start = models.DateField(
        "Début de période",
    )

    period_end = models.DateField(
        "Fin de période",
    )

    turnover = models.DecimalField(
        "Chiffre d'affaires",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    operating_expenses = models.DecimalField(
        "Charges d'exploitation",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    taxes = models.DecimalField(
        "Impôts et taxes",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    depreciation = models.DecimalField(
        "Amortissements",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    management_fees = models.DecimalField(
        "Frais de gestion et d'accompagnement",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    net_profit = models.DecimalField(
        "Résultat net",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    total_assets = models.DecimalField(
        "Total des actifs",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    total_liabilities = models.DecimalField(
        "Total des passifs",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    cash_balance = models.DecimalField(
        "Trésorerie",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_project_statements",
        verbose_name="Vérifié par",
    )

    approved_at = models.DateTimeField(
        "Approuvé le",
        null=True,
        blank=True,
    )

    notes = models.TextField(
        "Observations",
        blank=True,
    )

    class Meta:
        ordering = ["-period_end"]
        verbose_name = "État financier du projet"
        verbose_name_plural = "États financiers des projets"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "project",
                    "period_start",
                    "period_end",
                ],
                name="ci_unique_statement_period",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        if self.period_end < self.period_start:
            raise ValidationError(
                {
                    "period_end": (
                        "La fin de période doit être postérieure "
                        "au début de période."
                    )
                }
            )

    @property
    def return_on_investment(self) -> Decimal:
        capital = self.project.total_recognized_capital

        if capital <= ZERO_MONEY:
            return ZERO_MONEY

        return (
            self.net_profit
            / capital
            * HUNDRED_PERCENT
        )

    def __str__(self) -> str:
        return (
            f"{self.project.reference} — "
            f"{self.period_start} au {self.period_end}"
        )


# ==========================================================
# AFFECTATION DU BÉNÉFICE
# ==========================================================

class ProfitAllocation(TimeStampedModel):
    financial_statement = models.OneToOneField(
        ProjectFinancialStatement,
        on_delete=models.CASCADE,
        related_name="profit_allocation",
        verbose_name="État financier",
    )

    legal_reserve = models.DecimalField(
        "Réserve légale",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    operating_reserve = models.DecimalField(
        "Réserve d'exploitation",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    maintenance_fund = models.DecimalField(
        "Fonds de maintenance",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    risk_fund = models.DecimalField(
        "Fonds de sécurité",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    reinvestment_amount = models.DecimalField(
        "Montant réinvesti",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    distributable_profit = models.DecimalField(
        "Bénéfice distribuable",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    resolution_reference = models.CharField(
        "Référence de la décision",
        max_length=120,
        blank=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_profit_allocations",
        verbose_name="Approuvé par",
    )

    approved_at = models.DateTimeField(
        "Approuvé le",
        null=True,
        blank=True,
    )

    @property
    def total_allocated(self) -> Decimal:
        return (
            self.legal_reserve
            + self.operating_reserve
            + self.maintenance_fund
            + self.risk_fund
            + self.reinvestment_amount
            + self.distributable_profit
        )

    def clean(self) -> None:
        super().clean()

        if (
            self.financial_statement.net_profit >= ZERO_MONEY
            and self.total_allocated
            > self.financial_statement.net_profit
        ):
            raise ValidationError(
                "Le total affecté ne peut pas dépasser "
                "le bénéfice net."
            )

    def __str__(self) -> str:
        return (
            "Affectation — "
            f"{self.financial_statement.project.reference}"
        )


# ==========================================================
# DIVIDENDES
# ==========================================================

class DividendDeclaration(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        APPROVED = "APPROVED", "Approuvée"
        PAYMENT_IN_PROGRESS = (
            "PAYMENT_IN_PROGRESS",
            "Paiement en cours",
        )
        PAID = "PAID", "Entièrement payée"
        CANCELLED = "CANCELLED", "Annulée"

    profit_allocation = models.OneToOneField(
        ProfitAllocation,
        on_delete=models.CASCADE,
        related_name="dividend_declaration",
        verbose_name="Affectation du résultat",
    )

    declared_amount = models.DecimalField(
        "Montant total déclaré",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    declaration_date = models.DateField(
        "Date de déclaration",
        default=timezone.localdate,
    )

    planned_payment_date = models.DateField(
        "Date prévue de paiement",
        null=True,
        blank=True,
    )

    status = models.CharField(
        "Statut",
        max_length=25,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    resolution_reference = models.CharField(
        "Référence de la décision",
        max_length=120,
        blank=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_dividend_declarations",
        verbose_name="Approuvée par",
    )

    def clean(self) -> None:
        super().clean()

        if (
            self.declared_amount
            > self.profit_allocation.distributable_profit
        ):
            raise ValidationError(
                {
                    "declared_amount": (
                        "Le montant déclaré ne peut pas dépasser "
                        "le bénéfice distribuable."
                    )
                }
            )

    @property
    def total_entitlements(self) -> Decimal:
        result = self.entitlements.aggregate(
            total=Sum("gross_amount"),
        )

        return money_or_zero(result["total"])

    def __str__(self) -> str:
        project = (
            self.profit_allocation
            .financial_statement
            .project
        )

        return f"Dividendes — {project.reference}"


class DividendEntitlement(TimeStampedModel):
    declaration = models.ForeignKey(
        DividendDeclaration,
        on_delete=models.CASCADE,
        related_name="entitlements",
        verbose_name="Déclaration",
    )

    stakeholder = models.ForeignKey(
        ProjectStakeholder,
        on_delete=models.PROTECT,
        related_name="dividend_entitlements",
        verbose_name="Associé ou actionnaire",
    )

    ownership_percentage_snapshot = models.DecimalField(
        "Participation retenue (%)",
        max_digits=7,
        decimal_places=4,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    gross_amount = models.DecimalField(
        "Montant brut",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    withholding_amount = models.DecimalField(
        "Retenues",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    net_amount = models.DecimalField(
        "Montant net",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
        ],
    )

    class Meta:
        verbose_name = "Droit aux dividendes"
        verbose_name_plural = "Droits aux dividendes"

        constraints = [
            models.UniqueConstraint(
                fields=["declaration", "stakeholder"],
                name="ci_unique_dividend_holder",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        project = (
            self.declaration
            .profit_allocation
            .financial_statement
            .project
        )

        errors = {}

        if self.stakeholder.project_id != project.id:
            errors["stakeholder"] = (
                "L'associé ou actionnaire doit appartenir "
                "au projet concerné."
            )

        if self.withholding_amount > self.gross_amount:
            errors["withholding_amount"] = (
                "Les retenues ne peuvent pas dépasser "
                "le montant brut."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.net_amount = (
            self.gross_amount
            - self.withholding_amount
        )

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return (
            f"{self.stakeholder.legal_name} — "
            f"{self.net_amount} FCFA"
        )


class DividendPayment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        PROCESSING = "PROCESSING", "En traitement"
        PAID = "PAID", "Payé"
        FAILED = "FAILED", "Échec"
        CANCELLED = "CANCELLED", "Annulé"

    entitlement = models.ForeignKey(
        DividendEntitlement,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="Droit aux dividendes",
    )

    amount = models.DecimalField(
        "Montant payé",
        max_digits=18,
        decimal_places=2,
        validators=[
            MinValueValidator(ONE_CENT),
        ],
    )

    payment_date = models.DateField(
        "Date de paiement",
        null=True,
        blank=True,
    )

    payment_method = models.CharField(
        "Mode de paiement",
        max_length=60,
        blank=True,
    )

    transaction_reference = models.CharField(
        "Référence de transaction",
        max_length=150,
        blank=True,
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_dividend_payments",
        verbose_name="Traité par",
    )

    def clean(self) -> None:
        super().clean()

        already_paid = money_or_zero(
            self.entitlement.payments
            .exclude(pk=self.pk)
            .filter(status=self.Status.PAID)
            .aggregate(total=Sum("amount"))["total"]
        )

        if (
            already_paid + self.amount
            > self.entitlement.net_amount
        ):
            raise ValidationError(
                {
                    "amount": (
                        "Le cumul des paiements ne peut pas dépasser "
                        "le montant net dû."
                    )
                }
            )

    def __str__(self) -> str:
        return (
            f"{self.entitlement.stakeholder.legal_name} — "
            f"{self.amount} FCFA"
        )


# ==========================================================
# RÉINVESTISSEMENT
# ==========================================================

class ReinvestmentDecision(TimeStampedModel):
    source_project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.PROTECT,
        related_name="outgoing_reinvestments",
        verbose_name="Projet source",
    )

    destination_project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_reinvestments",
        verbose_name="Projet destinataire",
    )

    amount = models.DecimalField(
        "Montant réinvesti",
        max_digits=18,
        decimal_places=2,
        validators=[
            MinValueValidator(ONE_CENT),
        ],
    )

    decision_date = models.DateField(
        "Date de décision",
        default=timezone.localdate,
    )

    resolution_reference = models.CharField(
        "Référence de la décision",
        max_length=120,
    )

    description = models.TextField(
        "Objet du réinvestissement",
        blank=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_reinvestments",
        verbose_name="Approuvé par",
    )

    def clean(self) -> None:
        super().clean()

        if (
            self.destination_project_id
            and self.destination_project_id
            == self.source_project_id
        ):
            raise ValidationError(
                {
                    "destination_project": (
                        "Le projet destinataire doit être différent "
                        "du projet source."
                    )
                }
            )

    def __str__(self) -> str:
        return (
            f"Réinvestissement {self.source_project.reference} — "
            f"{self.amount} FCFA"
        )


# ==========================================================
# ÉTAPES DU PROJET
# ==========================================================

class ProjectMilestone(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planifiée"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        COMPLETED = "COMPLETED", "Terminée"
        DELAYED = "DELAYED", "En retard"
        CANCELLED = "CANCELLED", "Annulée"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="milestones",
        verbose_name="Projet",
    )

    title = models.CharField(
        "Étape",
        max_length=255,
    )

    description = models.TextField(
        "Description",
        blank=True,
    )

    planned_start_date = models.DateField(
        "Début prévu",
        null=True,
        blank=True,
    )

    planned_end_date = models.DateField(
        "Fin prévue",
        null=True,
        blank=True,
    )

    actual_end_date = models.DateField(
        "Date de réalisation",
        null=True,
        blank=True,
    )

    planned_budget = models.DecimalField(
        "Budget prévu",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    actual_cost = models.DecimalField(
        "Coût réel",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    progress_percentage = models.DecimalField(
        "Avancement (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO_MONEY,
        validators=[
            MinValueValidator(ZERO_MONEY),
            MaxValueValidator(HUNDRED_PERCENT),
        ],
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )

    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_project_milestones",
        verbose_name="Responsable",
    )

    class Meta:
        ordering = ["planned_end_date", "created_at"]
        verbose_name = "Étape du projet"
        verbose_name_plural = "Étapes des projets"

    def clean(self) -> None:
        super().clean()

        if (
            self.planned_start_date
            and self.planned_end_date
            and self.planned_end_date < self.planned_start_date
        ):
            raise ValidationError(
                {
                    "planned_end_date": (
                        "La date de fin doit être postérieure "
                        "à la date de début."
                    )
                }
            )

    def __str__(self) -> str:
        return f"{self.project.reference} — {self.title}"


# ==========================================================
# INCIDENTS
# ==========================================================

class ProjectIncident(TimeStampedModel):
    class Severity(models.TextChoices):
        LOW = "LOW", "Faible"
        MODERATE = "MODERATE", "Modérée"
        HIGH = "HIGH", "Élevée"
        CRITICAL = "CRITICAL", "Critique"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Ouvert"
        UNDER_REVIEW = "UNDER_REVIEW", "En analyse"
        CORRECTIVE_ACTION = (
            "CORRECTIVE_ACTION",
            "Action corrective",
        )
        RESOLVED = "RESOLVED", "Résolu"
        CLOSED = "CLOSED", "Clos"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="incidents",
        verbose_name="Projet",
    )

    title = models.CharField(
        "Titre",
        max_length=255,
    )

    description = models.TextField(
        "Description",
    )

    severity = models.CharField(
        "Gravité",
        max_length=20,
        choices=Severity.choices,
        default=Severity.MODERATE,
    )

    status = models.CharField(
        "Statut",
        max_length=25,
        choices=Status.choices,
        default=Status.OPEN,
    )

    corrective_action = models.TextField(
        "Action corrective",
        blank=True,
    )

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_project_incidents",
        verbose_name="Signalé par",
    )

    reported_at = models.DateTimeField(
        "Signalé le",
        auto_now_add=True,
    )

    resolved_at = models.DateTimeField(
        "Résolu le",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-reported_at"]
        verbose_name = "Incident du projet"
        verbose_name_plural = "Incidents des projets"

    def __str__(self) -> str:
        return f"{self.project.reference} — {self.title}"


# ==========================================================
# RÉUNIONS
# ==========================================================

class ProjectMeeting(TimeStampedModel):
    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="meetings",
        verbose_name="Projet",
    )

    meeting_date = models.DateTimeField(
        "Date et heure",
    )

    title = models.CharField(
        "Objet de la réunion",
        max_length=255,
    )

    agenda = models.TextField(
        "Ordre du jour",
        blank=True,
    )

    minutes = models.TextField(
        "Compte rendu",
        blank=True,
    )

    decisions = models.TextField(
        "Décisions",
        blank=True,
    )

    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="community_investment_meetings",
        verbose_name="Participants",
    )

    organized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organized_project_meetings",
        verbose_name="Organisée par",
    )

    class Meta:
        ordering = ["-meeting_date"]
        verbose_name = "Réunion du projet"
        verbose_name_plural = "Réunions des projets"

    def __str__(self) -> str:
        return f"{self.project.reference} — {self.title}"


# ==========================================================
# DOCUMENTS
# ==========================================================

class ProjectDocument(TimeStampedModel):
    class DocumentType(models.TextChoices):
        BUSINESS_PLAN = "BUSINESS_PLAN", "Plan d'affaires"
        FEASIBILITY_STUDY = (
            "FEASIBILITY_STUDY",
            "Étude de faisabilité",
        )
        RESOLUTION = "RESOLUTION", "Résolution du groupement"
        STATUTES = "STATUTES", "Statuts"
        INVESTMENT_AGREEMENT = (
            "INVESTMENT_AGREEMENT",
            "Convention d'investissement",
        )
        SHAREHOLDERS_AGREEMENT = (
            "SHAREHOLDERS_AGREEMENT",
            "Pacte d'associés ou d'actionnaires",
        )
        VALUATION_REPORT = (
            "VALUATION_REPORT",
            "Rapport de valorisation",
        )
        CONTRACT = "CONTRACT", "Contrat"
        INVOICE = "INVOICE", "Facture"
        FINANCIAL_REPORT = (
            "FINANCIAL_REPORT",
            "Rapport financier",
        )
        ACTIVITY_REPORT = (
            "ACTIVITY_REPORT",
            "Rapport d'activité",
        )
        PHOTO = "PHOTO", "Photographie"
        OTHER = "OTHER", "Autre"

    project = models.ForeignKey(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="Projet",
    )

    document_type = models.CharField(
        "Type de document",
        max_length=40,
        choices=DocumentType.choices,
    )

    title = models.CharField(
        "Titre",
        max_length=255,
    )

    file = models.FileField(
        "Fichier",
        upload_to=project_document_upload_to,
    )

    version = models.CharField(
        "Version",
        max_length=30,
        blank=True,
    )

    is_validated = models.BooleanField(
        "Document validé",
        default=False,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_project_documents",
        verbose_name="Déposé par",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Document du projet"
        verbose_name_plural = "Documents des projets"

    def __str__(self) -> str:
        return f"{self.project.reference} — {self.title}"


# ==========================================================
# IMPACT COMMUNAUTAIRE
# ==========================================================

class CommunityImpact(TimeStampedModel):
    project = models.OneToOneField(
        CommunityInvestmentProject,
        on_delete=models.CASCADE,
        related_name="impact",
        verbose_name="Projet",
    )

    jobs_created = models.PositiveIntegerField(
        "Emplois créés",
        default=0,
    )

    direct_beneficiaries = models.PositiveIntegerField(
        "Bénéficiaires directs",
        default=0,
    )

    indirect_beneficiaries = models.PositiveIntegerField(
        "Bénéficiaires indirects",
        default=0,
    )

    women_beneficiaries = models.PositiveIntegerField(
        "Femmes bénéficiaires",
        default=0,
    )

    youth_beneficiaries = models.PositiveIntegerField(
        "Jeunes bénéficiaires",
        default=0,
    )

    communities_impacted = models.PositiveIntegerField(
        "Communautés ou localités touchées",
        default=0,
    )

    annual_income_generated = models.DecimalField(
        "Revenus annuels générés",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    assets_created_value = models.DecimalField(
        "Valeur des actifs créés",
        max_digits=18,
        decimal_places=2,
        default=ZERO_MONEY,
    )

    environmental_benefits = models.TextField(
        "Bénéfices environnementaux",
        blank=True,
    )

    social_benefits = models.TextField(
        "Bénéfices sociaux",
        blank=True,
    )

    measurement_date = models.DateField(
        "Date de mesure",
        default=timezone.localdate,
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_project_impacts",
        verbose_name="Vérifié par",
    )

    class Meta:
        verbose_name = "Impact communautaire"
        verbose_name_plural = "Impacts communautaires"

    def __str__(self) -> str:
        return f"Impact — {self.project.reference}"