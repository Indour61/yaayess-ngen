from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class WeeklyExecutiveDashboard(models.Model):
    class ProjectStatus(models.TextChoices):
        GREEN = "GREEN", "Vert — Conforme"
        YELLOW = "YELLOW", "Jaune — Vigilance"
        RED = "RED", "Rouge — Critique"

    week_number = models.PositiveSmallIntegerField(
        "Numéro de semaine",
        validators=[
            MinValueValidator(1),
            MaxValueValidator(13),
        ],
    )

    period_start = models.DateField("Début de période")
    period_end = models.DateField("Fin de période")

    overall_status = models.CharField(
        "État général",
        max_length=10,
        choices=ProjectStatus.choices,
        default=ProjectStatus.GREEN,
    )

    progress_percentage = models.DecimalField(
        "Avancement global (%)",
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100),
        ],
    )

    # État des principaux domaines
    planning_status = models.CharField(
        "Planning",
        max_length=10,
        choices=ProjectStatus.choices,
        default=ProjectStatus.GREEN,
    )

    budget_status = models.CharField(
        "Budget",
        max_length=10,
        choices=ProjectStatus.choices,
        default=ProjectStatus.GREEN,
    )

    quality_status = models.CharField(
        "Qualité",
        max_length=10,
        choices=ProjectStatus.choices,
        default=ProjectStatus.GREEN,
    )

    platform_status = models.CharField(
        "Plateforme",
        max_length=10,
        choices=ProjectStatus.choices,
        default=ProjectStatus.GREEN,
    )

    user_satisfaction_status = models.CharField(
        "Satisfaction des utilisateurs",
        max_length=10,
        choices=ProjectStatus.choices,
        default=ProjectStatus.GREEN,
    )

    # KPI d’adoption
    accounts_created = models.PositiveIntegerField(
        "Comptes créés",
        default=0,
    )

    active_users = models.PositiveIntegerField(
        "Utilisateurs actifs",
        default=0,
    )

    groups_created = models.PositiveIntegerField(
        "Groupes créés",
        default=0,
    )

    registered_members = models.PositiveIntegerField(
        "Membres inscrits",
        default=0,
    )

    # KPI financiers
    contributions_count = models.PositiveIntegerField(
        "Nombre de cotisations",
        default=0,
    )

    contributions_amount = models.DecimalField(
        "Montant des cotisations",
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    savings_deposits_count = models.PositiveIntegerField(
        "Nombre de dépôts d’épargne",
        default=0,
    )

    savings_amount = models.DecimalField(
        "Montant total de l’épargne",
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    credits_granted_count = models.PositiveIntegerField(
        "Crédits accordés",
        default=0,
    )

    credits_amount = models.DecimalField(
        "Montant total des crédits",
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    repayments_count = models.PositiveIntegerField(
        "Remboursements réalisés",
        default=0,
    )

    investments_count = models.PositiveIntegerField(
        "Projets d’investissement",
        default=0,
    )

    investments_amount = models.DecimalField(
        "Montant total investi",
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    # KPI techniques
    platform_availability = models.DecimalField(
        "Disponibilité de la plateforme (%)",
        max_digits=5,
        decimal_places=2,
        default=100,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100),
        ],
    )

    successful_transaction_rate = models.DecimalField(
        "Taux de réussite des transactions (%)",
        max_digits=5,
        decimal_places=2,
        default=100,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100),
        ],
    )

    average_response_time = models.DecimalField(
        "Temps moyen de réponse (secondes)",
        max_digits=8,
        decimal_places=2,
        default=0,
    )

    critical_incidents = models.PositiveIntegerField(
        "Incidents critiques",
        default=0,
    )

    # Informations exécutives
    highlights = models.TextField(
        "Faits marquants",
        blank=True,
    )

    achievements = models.TextField(
        "Réalisations majeures",
        blank=True,
    )

    difficulties = models.TextField(
        "Difficultés rencontrées",
        blank=True,
    )

    opportunities = models.TextField(
        "Opportunités identifiées",
        blank=True,
    )

    major_risks = models.TextField(
        "Risques majeurs",
        blank=True,
    )

    expected_decisions = models.TextField(
        "Décisions attendues",
        blank=True,
    )

    next_week_priorities = models.TextField(
        "Priorités de la semaine suivante",
        blank=True,
    )

    project_manager_comment = models.TextField(
        "Commentaire du chef de projet",
        blank=True,
    )

    is_published = models.BooleanField(
        "Publié",
        default=False,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_executive_dashboards",
        verbose_name="Créé par",
    )

    created_at = models.DateTimeField(
        "Créé le",
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        "Mis à jour le",
        auto_now=True,
    )

    class Meta:
        ordering = ["-period_end", "-week_number"]
        verbose_name = "Tableau de bord exécutif"
        verbose_name_plural = "Tableaux de bord exécutifs"
        constraints = [
            models.UniqueConstraint(
                fields=["week_number", "period_start", "period_end"],
                name="unique_executive_dashboard_period",
            ),
        ]
        permissions = [
            (
                "access_executive_dashboard",
                "Peut accéder au tableau de bord exécutif",
            ),
        ]

    def __str__(self):
        return (
            f"Tableau de bord — Semaine {self.week_number} "
            f"({self.period_start} au {self.period_end})"
        )