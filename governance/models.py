from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth.models import Group as AuthGroup
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


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
# WORKFLOW DE GOUVERNANCE
# ==========================================================

class GovernanceWorkflow(TimeStampedModel):
    """
    Définit un processus configurable de gouvernance.

    Exemple :
    - investissement communautaire standard ;
    - investissement agricole ;
    - investissement à fort impact ;
    - procédure simplifiée.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        ACTIVE = "ACTIVE", "Actif"
        SUSPENDED = "SUSPENDED", "Suspendu"
        ARCHIVED = "ARCHIVED", "Archivé"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    code = models.CharField(
        "Code du workflow",
        max_length=60,
    )

    name = models.CharField(
        "Nom du workflow",
        max_length=180,
    )

    description = models.TextField(
        "Description",
        blank=True,
    )

    version = models.PositiveIntegerField(
        "Version",
        default=1,
        validators=[
            MinValueValidator(1),
        ],
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    is_default = models.BooleanField(
        "Workflow par défaut",
        default=False,
        help_text=(
            "Ce workflow sera utilisé par défaut lors de la création "
            "d'un nouveau dossier d'investissement."
        ),
    )

    allow_parallel_tasks = models.BooleanField(
        "Autoriser les tâches parallèles",
        default=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_governance_workflows",
        verbose_name="Créé par",
    )

    activated_at = models.DateTimeField(
        "Activé le",
        null=True,
        blank=True,
    )

    archived_at = models.DateTimeField(
        "Archivé le",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "code",
            "-version",
        ]

        verbose_name = "Workflow de gouvernance"
        verbose_name_plural = "Workflows de gouvernance"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "code",
                    "version",
                ],
                name="gov_unique_workflow_version",
            ),
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="gov_only_one_default_workflow",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "status",
                    "is_default",
                ],
                name="gov_workflow_status_idx",
            ),
            models.Index(
                fields=[
                    "code",
                    "version",
                ],
                name="gov_workflow_code_idx",
            ),
        ]

        permissions = [
            (
                "manage_governance_workflows",
                "Peut gérer les workflows de gouvernance",
            ),
            (
                "view_governance_dashboard",
                "Peut consulter le tableau de bord de gouvernance",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if self.is_default and self.status != self.Status.ACTIVE:
            errors["is_default"] = (
                "Seul un workflow actif peut devenir le workflow "
                "par défaut."
            )

        if (
            self.status == self.Status.ACTIVE
            and self.pk
            and not self.stages.filter(is_active=True).exists()
        ):
            errors["status"] = (
                "Le workflow doit comporter au moins une étape active "
                "avant son activation."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.code = self.code.strip().upper().replace(" ", "_")
        self.name = self.name.strip()

        if self.status == self.Status.ACTIVE and self.activated_at is None:
            self.activated_at = timezone.now()

        if self.status == self.Status.ARCHIVED and self.archived_at is None:
            self.archived_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def first_stage(self):
        return (
            self.stages
            .filter(
                is_active=True,
                is_initial=True,
            )
            .order_by(
                "order",
            )
            .first()
        )

    @property
    def final_stages(self):
        return self.stages.filter(
            is_active=True,
            is_final=True,
        )

    def __str__(self) -> str:
        return f"{self.name} — v{self.version}"


# ==========================================================
# ÉTAPE DU WORKFLOW
# ==========================================================

class GovernanceStage(TimeStampedModel):
    """
    Représente une étape du workflow.

    Exemples :
    - pré-éligibilité ;
    - instruction du bureau de poste ;
    - validation régionale ;
    - comité d'investissement ;
    - structuration juridique.
    """

    class StageType(models.TextChoices):
        AUTOMATED = "AUTOMATED", "Traitement automatique"
        REVIEW = "REVIEW", "Instruction"
        APPROVAL = "APPROVAL", "Approbation"
        COMMITTEE = "COMMITTEE", "Comité"
        LEGAL = "LEGAL", "Structuration juridique"
        EXECUTION = "EXECUTION", "Exécution"
        AUDIT = "AUDIT", "Audit et contrôle"
        FINANCIAL = "FINANCIAL", "Traitement financier"
        CLOSURE = "CLOSURE", "Clôture"
        OTHER = "OTHER", "Autre"

    workflow = models.ForeignKey(
        GovernanceWorkflow,
        on_delete=models.CASCADE,
        related_name="stages",
        verbose_name="Workflow",
    )

    code = models.CharField(
        "Code de l'étape",
        max_length=60,
    )

    name = models.CharField(
        "Nom de l'étape",
        max_length=180,
    )

    description = models.TextField(
        "Description",
        blank=True,
    )

    stage_type = models.CharField(
        "Type d'étape",
        max_length=20,
        choices=StageType.choices,
        default=StageType.REVIEW,
    )

    order = models.PositiveIntegerField(
        "Ordre",
        default=10,
        validators=[
            MinValueValidator(1),
        ],
    )

    is_initial = models.BooleanField(
        "Étape initiale",
        default=False,
    )

    is_final = models.BooleanField(
        "Étape finale",
        default=False,
    )

    is_active = models.BooleanField(
        "Étape active",
        default=True,
    )

    is_mandatory = models.BooleanField(
        "Étape obligatoire",
        default=True,
    )

    requires_decision = models.BooleanField(
        "Décision requise",
        default=True,
    )

    requires_comment = models.BooleanField(
        "Commentaire obligatoire",
        default=False,
    )

    requires_document = models.BooleanField(
        "Document obligatoire",
        default=False,
    )

    responsible_group = models.ForeignKey(
        AuthGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="governance_stages",
        verbose_name="Groupe responsable",
    )

    target_duration_days = models.PositiveIntegerField(
        "Délai cible en jours",
        default=3,
        validators=[
            MinValueValidator(1),
        ],
    )

    escalation_after_days = models.PositiveIntegerField(
        "Escalade après un nombre de jours",
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1),
        ],
    )

    instructions = models.TextField(
        "Instructions",
        blank=True,
    )

    class Meta:
        ordering = [
            "workflow",
            "order",
        ]

        verbose_name = "Étape de gouvernance"
        verbose_name_plural = "Étapes de gouvernance"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "workflow",
                    "code",
                ],
                name="gov_unique_stage_code",
            ),
            models.UniqueConstraint(
                fields=[
                    "workflow",
                    "order",
                ],
                name="gov_unique_stage_order",
            ),
            models.UniqueConstraint(
                fields=["workflow"],
                condition=Q(is_initial=True),
                name="gov_one_initial_stage",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "workflow",
                    "order",
                    "is_active",
                ],
                name="gov_stage_order_idx",
            ),
            models.Index(
                fields=[
                    "stage_type",
                    "is_active",
                ],
                name="gov_stage_type_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if self.is_initial and self.is_final:
            errors["is_final"] = (
                "Une étape ne peut pas être initiale et finale "
                "simultanément."
            )

        if (
            self.escalation_after_days is not None
            and self.escalation_after_days < self.target_duration_days
        ):
            errors["escalation_after_days"] = (
                "Le délai d'escalade doit être supérieur ou égal "
                "au délai cible."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.code = self.code.strip().upper().replace(" ", "_")
        self.name = self.name.strip()

        super().save(*args, **kwargs)

    @property
    def next_transitions(self):
        return self.outgoing_transitions.filter(
            is_active=True,
        )

    def __str__(self) -> str:
        return (
            f"{self.workflow.code} — "
            f"{self.order}. {self.name}"
        )


# ==========================================================
# TRANSITION ENTRE DEUX ÉTAPES
# ==========================================================

class GovernanceTransition(TimeStampedModel):
    """
    Définit un passage autorisé entre deux étapes.

    Une transition peut représenter :
    - une approbation ;
    - un rejet ;
    - une demande de complément ;
    - un retour à une étape précédente ;
    - une suspension ;
    - une reprise.
    """

    class Trigger(models.TextChoices):
        APPROVE = "APPROVE", "Approuver"
        REJECT = "REJECT", "Rejeter"
        REQUEST_INFO = (
            "REQUEST_INFO",
            "Demander des informations complémentaires",
        )
        RETURN = "RETURN", "Retourner à l'étape précédente"
        SUBMIT = "SUBMIT", "Soumettre"
        COMPLETE = "COMPLETE", "Terminer"
        SUSPEND = "SUSPEND", "Suspendre"
        RESUME = "RESUME", "Reprendre"
        AUTOMATIC = "AUTOMATIC", "Transition automatique"
        CANCEL = "CANCEL", "Annuler"

    workflow = models.ForeignKey(
        GovernanceWorkflow,
        on_delete=models.CASCADE,
        related_name="transitions",
        verbose_name="Workflow",
    )

    name = models.CharField(
        "Nom de la transition",
        max_length=180,
    )

    code = models.CharField(
        "Code de la transition",
        max_length=60,
    )

    from_stage = models.ForeignKey(
        GovernanceStage,
        on_delete=models.CASCADE,
        related_name="outgoing_transitions",
        verbose_name="Étape de départ",
    )

    to_stage = models.ForeignKey(
        GovernanceStage,
        on_delete=models.CASCADE,
        related_name="incoming_transitions",
        verbose_name="Étape d'arrivée",
    )

    trigger = models.CharField(
        "Action déclenchante",
        max_length=20,
        choices=Trigger.choices,
    )

    is_active = models.BooleanField(
        "Transition active",
        default=True,
    )

    requires_comment = models.BooleanField(
        "Commentaire obligatoire",
        default=False,
    )

    requires_document = models.BooleanField(
        "Document obligatoire",
        default=False,
    )

    requires_permission = models.CharField(
        "Permission Django requise",
        max_length=150,
        blank=True,
        help_text=(
            "Exemple : governance.approve_governance_decision. "
            "Laisser vide si aucune permission spécifique n'est requise."
        ),
    )

    minimum_score = models.DecimalField(
        "Score minimal requis",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Score minimal nécessaire pour autoriser cette transition."
        ),
    )

    condition_description = models.TextField(
        "Description des conditions",
        blank=True,
    )

    class Meta:
        ordering = [
            "workflow",
            "from_stage__order",
            "to_stage__order",
        ]

        verbose_name = "Transition de gouvernance"
        verbose_name_plural = "Transitions de gouvernance"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "workflow",
                    "code",
                ],
                name="gov_unique_transition_code",
            ),
            models.UniqueConstraint(
                fields=[
                    "from_stage",
                    "to_stage",
                    "trigger",
                ],
                name="gov_unique_stage_transition",
            ),
            models.CheckConstraint(
                condition=(
                    Q(minimum_score__isnull=True)
                    | (
                        Q(minimum_score__gte=0)
                        & Q(minimum_score__lte=100)
                    )
                ),
                name="gov_transition_score_valid",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "workflow",
                    "is_active",
                ],
                name="gov_transition_active_idx",
            ),
            models.Index(
                fields=[
                    "from_stage",
                    "trigger",
                ],
                name="gov_transition_trigger_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if self.from_stage_id and self.to_stage_id:
            if self.from_stage_id == self.to_stage_id:
                errors["to_stage"] = (
                    "L'étape d'arrivée doit être différente "
                    "de l'étape de départ."
                )

            if self.from_stage.workflow_id != self.workflow_id:
                errors["from_stage"] = (
                    "L'étape de départ doit appartenir au workflow."
                )

            if self.to_stage.workflow_id != self.workflow_id:
                errors["to_stage"] = (
                    "L'étape d'arrivée doit appartenir au workflow."
                )

            if self.from_stage.is_final:
                errors["from_stage"] = (
                    "Une étape finale ne peut pas avoir de transition "
                    "sortante."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.code = self.code.strip().upper().replace(" ", "_")
        self.name = self.name.strip()

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return (
            f"{self.from_stage.name} → "
            f"{self.to_stage.name} "
            f"({self.get_trigger_display()})"
        )


# ==========================================================
# INSTANCE DE WORKFLOW POUR UN PROJET
# ==========================================================

class GovernanceInstance(TimeStampedModel):
    """
    Instance réelle d'un workflow appliquée à un projet
    d'investissement communautaire.
    """

    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Non démarré"
        ACTIVE = "ACTIVE", "En cours"
        WAITING = "WAITING", "En attente"
        SUSPENDED = "SUSPENDED", "Suspendu"
        APPROVED = "APPROVED", "Approuvé"
        REJECTED = "REJECTED", "Rejeté"
        COMPLETED = "COMPLETED", "Terminé"
        CANCELLED = "CANCELLED", "Annulé"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    reference = models.CharField(
        "Référence",
        max_length=50,
        unique=True,
        editable=False,
    )

    project = models.OneToOneField(
        "community_investment.CommunityInvestmentProject",
        on_delete=models.CASCADE,
        related_name="governance_instance",
        verbose_name="Projet d'investissement",
    )

    workflow = models.ForeignKey(
        GovernanceWorkflow,
        on_delete=models.PROTECT,
        related_name="instances",
        verbose_name="Workflow",
    )

    current_stage = models.ForeignKey(
        GovernanceStage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_instances",
        verbose_name="Étape actuelle",
    )

    previous_stage = models.ForeignKey(
        GovernanceStage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="previous_instances",
        verbose_name="Étape précédente",
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )

    governance_score = models.DecimalField(
        "Score de gouvernance (%)",
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_governance_instances",
        verbose_name="Démarré par",
    )

    started_at = models.DateTimeField(
        "Démarré le",
        null=True,
        blank=True,
    )

    stage_started_at = models.DateTimeField(
        "Étape actuelle démarrée le",
        null=True,
        blank=True,
    )

    due_at = models.DateTimeField(
        "Échéance de l'étape actuelle",
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        "Terminé le",
        null=True,
        blank=True,
    )

    suspended_at = models.DateTimeField(
        "Suspendu le",
        null=True,
        blank=True,
    )

    suspension_reason = models.TextField(
        "Motif de suspension",
        blank=True,
    )

    rejection_reason = models.TextField(
        "Motif du rejet",
        blank=True,
    )

    last_action_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_updated_governance_instances",
        verbose_name="Dernière action réalisée par",
    )

    last_action_at = models.DateTimeField(
        "Dernière action le",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

        verbose_name = "Instance de gouvernance"
        verbose_name_plural = "Instances de gouvernance"

        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(governance_score__gte=0)
                    & Q(governance_score__lte=100)
                ),
                name="gov_instance_score_valid",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "status",
                    "current_stage",
                ],
                name="gov_instance_status_idx",
            ),
            models.Index(
                fields=[
                    "workflow",
                    "status",
                ],
                name="gov_instance_workflow_idx",
            ),
            models.Index(
                fields=[
                    "due_at",
                    "status",
                ],
                name="gov_instance_due_idx",
            ),
        ]

        permissions = [
            (
                "review_governance_case",
                "Peut instruire un dossier de gouvernance",
            ),
            (
                "approve_governance_decision",
                "Peut approuver une décision de gouvernance",
            ),
            (
                "audit_governance_case",
                "Peut auditer un dossier de gouvernance",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if (
            self.current_stage_id
            and self.current_stage.workflow_id != self.workflow_id
        ):
            errors["current_stage"] = (
                "L'étape actuelle doit appartenir au workflow "
                "de l'instance."
            )

        if (
            self.previous_stage_id
            and self.previous_stage.workflow_id != self.workflow_id
        ):
            errors["previous_stage"] = (
                "L'étape précédente doit appartenir au workflow "
                "de l'instance."
            )

        if (
            self.status == self.Status.SUSPENDED
            and not self.suspension_reason.strip()
        ):
            errors["suspension_reason"] = (
                "Le motif de suspension est obligatoire."
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

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = (
                f"GOV-{timezone.now():%Y%m%d}-"
                f"{uuid.uuid4().hex[:8].upper()}"
            )

        if (
            self.status == self.Status.ACTIVE
            and self.started_at is None
        ):
            self.started_at = timezone.now()

        if (
            self.status == self.Status.SUSPENDED
            and self.suspended_at is None
        ):
            self.suspended_at = timezone.now()

        if self.status in {
            self.Status.COMPLETED,
            self.Status.APPROVED,
            self.Status.REJECTED,
            self.Status.CANCELLED,
        } and self.completed_at is None:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.due_at
            and self.status in {
                self.Status.ACTIVE,
                self.Status.WAITING,
            }
            and timezone.now() > self.due_at
        )

    @property
    def open_tasks_count(self) -> int:
        return self.tasks.exclude(
            status__in=[
                GovernanceTask.Status.COMPLETED,
                GovernanceTask.Status.CANCELLED,
            ],
        ).count()

    def __str__(self) -> str:
        return (
            f"{self.reference} — "
            f"{self.project.title}"
        )


# ==========================================================
# TÂCHE DE GOUVERNANCE
# ==========================================================

class GovernanceTask(TimeStampedModel):
    """
    Tâche affectée à un utilisateur ou un groupe responsable
    dans le cadre d'une étape de gouvernance.
    """

    class TaskType(models.TextChoices):
        REVIEW = "REVIEW", "Instruction"
        VALIDATION = "VALIDATION", "Validation"
        DOCUMENT = "DOCUMENT", "Collecte ou contrôle documentaire"
        ANALYSIS = "ANALYSIS", "Analyse"
        VOTE = "VOTE", "Vote"
        SIGNATURE = "SIGNATURE", "Signature"
        AUDIT = "AUDIT", "Audit"
        FOLLOW_UP = "FOLLOW_UP", "Suivi"
        CORRECTIVE_ACTION = (
            "CORRECTIVE_ACTION",
            "Action corrective",
        )
        OTHER = "OTHER", "Autre"

    class Priority(models.TextChoices):
        LOW = "LOW", "Faible"
        NORMAL = "NORMAL", "Normale"
        HIGH = "HIGH", "Élevée"
        URGENT = "URGENT", "Urgente"
        CRITICAL = "CRITICAL", "Critique"

    class Status(models.TextChoices):
        PENDING = "PENDING", "À traiter"
        ASSIGNED = "ASSIGNED", "Assignée"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        WAITING = "WAITING", "En attente"
        COMPLETED = "COMPLETED", "Terminée"
        REJECTED = "REJECTED", "Rejetée"
        CANCELLED = "CANCELLED", "Annulée"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    reference = models.CharField(
        "Référence",
        max_length=50,
        unique=True,
        editable=False,
    )

    instance = models.ForeignKey(
        GovernanceInstance,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="Instance de gouvernance",
    )

    stage = models.ForeignKey(
        GovernanceStage,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="Étape",
    )

    title = models.CharField(
        "Titre",
        max_length=255,
    )

    description = models.TextField(
        "Description",
        blank=True,
    )

    task_type = models.CharField(
        "Type de tâche",
        max_length=30,
        choices=TaskType.choices,
        default=TaskType.REVIEW,
    )

    priority = models.CharField(
        "Priorité",
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )

    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_governance_tasks",
        verbose_name="Assignée à",
    )

    assigned_group = models.ForeignKey(
        AuthGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_governance_tasks",
        verbose_name="Groupe assigné",
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_governance_tasks",
        verbose_name="Assignée par",
    )

    assigned_at = models.DateTimeField(
        "Assignée le",
        null=True,
        blank=True,
    )

    started_at = models.DateTimeField(
        "Commencée le",
        null=True,
        blank=True,
    )

    due_at = models.DateTimeField(
        "Échéance",
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        "Terminée le",
        null=True,
        blank=True,
    )

    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_governance_tasks",
        verbose_name="Terminée par",
    )

    completion_comment = models.TextField(
        "Commentaire de traitement",
        blank=True,
    )

    result_data = models.JSONField(
        "Résultat structuré",
        default=dict,
        blank=True,
        help_text=(
            "Permet d'enregistrer des résultats techniques ou "
            "des données calculées au format JSON."
        ),
    )

    is_mandatory = models.BooleanField(
        "Tâche obligatoire",
        default=True,
    )

    class Meta:
        ordering = [
            "due_at",
            "-priority",
            "created_at",
        ]

        verbose_name = "Tâche de gouvernance"
        verbose_name_plural = "Tâches de gouvernance"

        indexes = [
            models.Index(
                fields=[
                    "status",
                    "priority",
                ],
                name="gov_task_status_idx",
            ),
            models.Index(
                fields=[
                    "assigned_to",
                    "status",
                ],
                name="gov_task_user_idx",
            ),
            models.Index(
                fields=[
                    "assigned_group",
                    "status",
                ],
                name="gov_task_group_idx",
            ),
            models.Index(
                fields=[
                    "due_at",
                    "status",
                ],
                name="gov_task_due_idx",
            ),
            models.Index(
                fields=[
                    "instance",
                    "stage",
                    "status",
                ],
                name="gov_task_instance_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if (
            self.instance_id
            and self.stage_id
            and self.stage.workflow_id != self.instance.workflow_id
        ):
            errors["stage"] = (
                "L'étape doit appartenir au workflow de l'instance."
            )

        if (
            self.assigned_to_id is None
            and self.assigned_group_id is None
            and self.status
            in {
                self.Status.ASSIGNED,
                self.Status.IN_PROGRESS,
            }
        ):
            errors["assigned_to"] = (
                "Une tâche assignée ou en cours doit être affectée "
                "à un utilisateur ou à un groupe."
            )

        if (
            self.status == self.Status.COMPLETED
            and not self.completion_comment.strip()
        ):
            errors["completion_comment"] = (
                "Un commentaire de traitement est obligatoire "
                "pour terminer la tâche."
            )

        if (
            self.started_at
            and self.completed_at
            and self.completed_at < self.started_at
        ):
            errors["completed_at"] = (
                "La date de fin ne peut pas être antérieure "
                "à la date de début."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = (
                f"TASK-{timezone.now():%Y%m%d}-"
                f"{uuid.uuid4().hex[:8].upper()}"
            )

        if (
            self.status == self.Status.ASSIGNED
            and self.assigned_at is None
        ):
            self.assigned_at = timezone.now()

        if (
            self.status == self.Status.IN_PROGRESS
            and self.started_at is None
        ):
            self.started_at = timezone.now()

        if (
            self.status == self.Status.COMPLETED
            and self.completed_at is None
        ):
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.due_at
            and self.status not in {
                self.Status.COMPLETED,
                self.Status.CANCELLED,
            }
            and timezone.now() > self.due_at
        )

    def __str__(self) -> str:
        return f"{self.reference} — {self.title}"

# ==========================================================
# JOURNAL DES DÉCISIONS DE GOUVERNANCE
# ==========================================================

class GovernanceDecisionLog(TimeStampedModel):
    """
    Piste d'audit des recommandations et décisions produites
    par le moteur de gouvernance.

    L'enregistrement conserve un instantané du résultat du moteur,
    du projet, des étapes et de l'acteur au moment de la décision.
    """

    class DecisionCode(models.TextChoices):
        APPROVE = "APPROVE", "Approuver"
        REJECT = "REJECT", "Rejeter"
        REQUEST_INFO = (
            "REQUEST_INFO",
            "Demander des informations complémentaires",
        )
        ADVANCE = "ADVANCE", "Passer à l'étape suivante"
        BLOCK = "BLOCK", "Bloquer"
        MANUAL_REVIEW = (
            "MANUAL_REVIEW",
            "Soumettre à une revue humaine",
        )

    class ApplicationStatus(models.TextChoices):
        RECOMMENDED = (
            "RECOMMENDED",
            "Recommandation uniquement",
        )
        APPLIED = "APPLIED", "Décision appliquée"
        NOT_APPLIED = "NOT_APPLIED", "Décision non appliquée"
        OVERRIDDEN = (
            "OVERRIDDEN",
            "Décision remplacée manuellement",
        )
        FAILED = "FAILED", "Échec lors de l'application"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    reference = models.CharField(
        "Référence",
        max_length=60,
        unique=True,
        editable=False,
    )

    instance = models.ForeignKey(
        GovernanceInstance,
        on_delete=models.PROTECT,
        related_name="decision_logs",
        verbose_name="Instance de gouvernance",
    )

    project = models.ForeignKey(
        "community_investment.CommunityInvestmentProject",
        on_delete=models.PROTECT,
        related_name="governance_decision_logs",
        verbose_name="Projet",
    )

    workflow = models.ForeignKey(
        GovernanceWorkflow,
        on_delete=models.PROTECT,
        related_name="decision_logs",
        verbose_name="Workflow",
    )

    from_stage = models.ForeignKey(
        GovernanceStage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="outgoing_decision_logs",
        verbose_name="Étape de départ",
    )

    to_stage = models.ForeignKey(
        GovernanceStage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_decision_logs",
        verbose_name="Étape d'arrivée",
    )

    transition = models.ForeignKey(
        GovernanceTransition,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="decision_logs",
        verbose_name="Transition utilisée",
    )

    decision_code = models.CharField(
        "Décision",
        max_length=30,
        choices=DecisionCode.choices,
    )

    application_status = models.CharField(
        "Statut d'application",
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.RECOMMENDED,
    )

    global_score = models.DecimalField(
        "Score global (%)",
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    eligible = models.BooleanField(
        "Dossier éligible",
        default=False,
    )

    can_advance = models.BooleanField(
        "Peut avancer",
        default=False,
    )

    summary = models.TextField(
        "Résumé de la décision",
        blank=True,
    )

    criteria_snapshot = models.JSONField(
        "Critères évalués",
        default=list,
        blank=True,
    )

    blocking_reasons = models.JSONField(
        "Motifs bloquants",
        default=list,
        blank=True,
    )

    warnings = models.JSONField(
        "Avertissements",
        default=list,
        blank=True,
    )

    engine_snapshot = models.JSONField(
        "Instantané complet du moteur",
        default=dict,
        blank=True,
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="governance_decision_logs",
        verbose_name="Acteur",
    )

    evaluated_at = models.DateTimeField(
        "Évalué le",
        default=timezone.now,
    )

    applied_at = models.DateTimeField(
        "Appliqué le",
        null=True,
        blank=True,
    )

    override_reason = models.TextField(
        "Motif du remplacement manuel",
        blank=True,
    )

    failure_message = models.TextField(
        "Message d'échec",
        blank=True,
    )

    actor_ip_address = models.GenericIPAddressField(
        "Adresse IP",
        null=True,
        blank=True,
    )

    actor_user_agent = models.TextField(
        "Navigateur ou client",
        blank=True,
    )

    class Meta:
        ordering = [
            "-evaluated_at",
            "-created_at",
        ]

        verbose_name = "Journal de décision"
        verbose_name_plural = "Journaux des décisions"

        indexes = [
            models.Index(
                fields=[
                    "instance",
                    "evaluated_at",
                ],
                name="gov_log_instance_idx",
            ),
            models.Index(
                fields=[
                    "project",
                    "decision_code",
                ],
                name="gov_log_project_idx",
            ),
            models.Index(
                fields=[
                    "application_status",
                    "evaluated_at",
                ],
                name="gov_log_status_idx",
            ),
            models.Index(
                fields=[
                    "workflow",
                    "from_stage",
                    "to_stage",
                ],
                name="gov_log_transition_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=(
                        Q(global_score__gte=0)
                        & Q(global_score__lte=100)
                ),
                name="gov_log_score_valid",
            ),
        ]

        permissions = [
            (
                "view_governance_audit_log",
                "Peut consulter le journal d'audit de gouvernance",
            ),
            (
                "override_governance_decision",
                "Peut remplacer une décision du moteur",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors = {}

        if self.instance_id:
            if self.project_id != self.instance.project_id:
                errors["project"] = (
                    "Le projet doit correspondre au projet "
                    "de l'instance."
                )

            if self.workflow_id != self.instance.workflow_id:
                errors["workflow"] = (
                    "Le workflow doit correspondre au workflow "
                    "de l'instance."
                )

        if self.from_stage_id:
            if self.from_stage.workflow_id != self.workflow_id:
                errors["from_stage"] = (
                    "L'étape de départ doit appartenir au workflow."
                )

        if self.to_stage_id:
            if self.to_stage.workflow_id != self.workflow_id:
                errors["to_stage"] = (
                    "L'étape d'arrivée doit appartenir au workflow."
                )

        if self.transition_id:
            if (
                    self.from_stage_id
                    and self.transition.from_stage_id
                    != self.from_stage_id
            ):
                errors["transition"] = (
                    "La transition ne correspond pas "
                    "à l'étape de départ."
                )

            if (
                    self.to_stage_id
                    and self.transition.to_stage_id
                    != self.to_stage_id
            ):
                errors["transition"] = (
                    "La transition ne correspond pas "
                    "à l'étape d'arrivée."
                )

            if self.transition.workflow_id != self.workflow_id:
                errors["transition"] = (
                    "La transition doit appartenir au workflow."
                )

        if (
                self.application_status
                == self.ApplicationStatus.APPLIED
                and self.applied_at is None
        ):
            errors["applied_at"] = (
                "La date d'application est obligatoire "
                "pour une décision appliquée."
            )

        if (
                self.application_status
                == self.ApplicationStatus.OVERRIDDEN
                and not self.override_reason.strip()
        ):
            errors["override_reason"] = (
                "Le motif du remplacement manuel est obligatoire."
            )

        if (
                self.application_status
                == self.ApplicationStatus.FAILED
                and not self.failure_message.strip()
        ):
            errors["failure_message"] = (
                "Le message d'échec est obligatoire."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = (
                f"GOV-LOG-{timezone.now():%Y%m%d}-"
                f"{uuid.uuid4().hex[:10].upper()}"
            )

        if (
                self.application_status
                == self.ApplicationStatus.APPLIED
                and self.applied_at is None
        ):
            self.applied_at = timezone.now()

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Un journal de décision de gouvernance "
            "ne peut pas être supprimé."
        )

    def __str__(self) -> str:
        return (
            f"{self.reference} — "
            f"{self.get_decision_code_display()} — "
            f"{self.global_score}%"
        )