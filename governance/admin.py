from __future__ import annotations
import json
from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    GovernanceDecisionLog,
    GovernanceInstance,
    GovernanceStage,
    GovernanceTask,
    GovernanceTransition,
    GovernanceWorkflow,
)


# ==========================================================
# OUTILS D'AFFICHAGE
# ==========================================================

def status_badge(label: str, color: str) -> str:
    return format_html(
        (
            '<span style="'
            'display:inline-block;'
            'padding:3px 9px;'
            'border-radius:12px;'
            'font-weight:700;'
            'font-size:12px;'
            'color:{};'
            'background:{}20;'
            'border:1px solid {}50;'
            '">'
            "● {}"
            "</span>"
        ),
        color,
        color,
        color,
        label,
    )

def percentage_badge(value) -> str:
    """
    Affiche un pourcentage avec une couleur adaptée.

    La valeur est formatée avant son passage à format_html(),
    car format_html transforme ses arguments en SafeString et
    ne prend pas en charge directement le format {:.2f}.
    """
    try:
        numeric_value = float(value or 0)
    except (TypeError, ValueError):
        numeric_value = 0.0

    if numeric_value >= 80:
        color = "#198754"
    elif numeric_value >= 60:
        color = "#0d6efd"
    elif numeric_value >= 40:
        color = "#fd7e14"
    else:
        color = "#dc3545"

    formatted_value = f"{numeric_value:.2f}"

    return format_html(
        '<strong style="color:{};">{} %</strong>',
        color,
        formatted_value,
    )

# ==========================================================
# INLINES DU WORKFLOW
# ==========================================================

class GovernanceStageInline(admin.TabularInline):
    model = GovernanceStage
    extra = 0
    show_change_link = True

    fields = (
        "order",
        "code",
        "name",
        "stage_type",
        "responsible_group",
        "target_duration_days",
        "is_initial",
        "is_final",
        "is_active",
    )

    ordering = (
        "order",
    )


class GovernanceTransitionInline(admin.TabularInline):
    model = GovernanceTransition
    fk_name = "workflow"
    extra = 0
    show_change_link = True

    fields = (
        "code",
        "name",
        "from_stage",
        "to_stage",
        "trigger",
        "minimum_score",
        "is_active",
    )


# ==========================================================
# INLINES DE L'INSTANCE
# ==========================================================

class GovernanceTaskInline(admin.TabularInline):
    model = GovernanceTask
    extra = 0
    show_change_link = True

    fields = (
        "reference",
        "stage",
        "title",
        "task_type",
        "priority",
        "status",
        "assigned_to",
        "assigned_group",
        "due_at",
    )

    readonly_fields = (
        "reference",
    )

    ordering = (
        "due_at",
        "-priority",
    )


# ==========================================================
# WORKFLOWS
# ==========================================================

@admin.register(GovernanceWorkflow)
class GovernanceWorkflowAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "version",
        "status_display",
        "default_display",
        "stage_count",
        "transition_count",
        "instance_count",
        "created_by",
        "updated_at",
    )

    list_filter = (
        "status",
        "is_default",
        "allow_parallel_tasks",
        "version",
        "created_at",
    )

    search_fields = (
        "code",
        "name",
        "description",
        "created_by__nom",
        "created_by__phone",
    )

    autocomplete_fields = (
        "created_by",
    )

    readonly_fields = (
        "activated_at",
        "archived_at",
        "stage_count_display",
        "transition_count_display",
        "instance_count_display",
        "created_at",
        "updated_at",
    )

    ordering = (
        "code",
        "-version",
    )

    save_on_top = True

    inlines = (
        GovernanceStageInline,
        GovernanceTransitionInline,
    )

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "code",
                    "name",
                    "description",
                    "version",
                )
            },
        ),
        (
            "Configuration",
            {
                "fields": (
                    "status",
                    "is_default",
                    "allow_parallel_tasks",
                )
            },
        ),
        (
            "Statistiques",
            {
                "fields": (
                    "stage_count_display",
                    "transition_count_display",
                    "instance_count_display",
                )
            },
        ),
        (
            "Traçabilité",
            {
                "fields": (
                    "created_by",
                    "activated_at",
                    "archived_at",
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    actions = (
        "activate_workflows",
        "suspend_workflows",
        "archive_workflows",
        "set_as_default",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("created_by")
            .annotate(
                admin_stage_count=Count(
                    "stages",
                    distinct=True,
                ),
                admin_transition_count=Count(
                    "transitions",
                    distinct=True,
                ),
                admin_instance_count=Count(
                    "instances",
                    distinct=True,
                ),
            )
        )

    @admin.display(description="Statut")
    def status_display(self, obj):
        colors = {
            obj.Status.DRAFT: "#6c757d",
            obj.Status.ACTIVE: "#198754",
            obj.Status.SUSPENDED: "#fd7e14",
            obj.Status.ARCHIVED: "#dc3545",
        }

        return status_badge(
            obj.get_status_display(),
            colors.get(obj.status, "#6c757d"),
        )

    @admin.display(description="Par défaut", boolean=True)
    def default_display(self, obj):
        return obj.is_default

    @admin.display(description="Étapes")
    def stage_count(self, obj):
        return obj.admin_stage_count

    @admin.display(description="Transitions")
    def transition_count(self, obj):
        return obj.admin_transition_count

    @admin.display(description="Instances")
    def instance_count(self, obj):
        return obj.admin_instance_count

    @admin.display(description="Nombre d'étapes")
    def stage_count_display(self, obj):
        if not obj.pk:
            return 0

        return obj.stages.count()

    @admin.display(description="Nombre de transitions")
    def transition_count_display(self, obj):
        if not obj.pk:
            return 0

        return obj.transitions.count()

    @admin.display(description="Nombre d'instances")
    def instance_count_display(self, obj):
        if not obj.pk:
            return 0

        return obj.instances.count()

    @admin.action(description="Activer les workflows sélectionnés")
    def activate_workflows(self, request, queryset):
        updated = queryset.update(
            status=GovernanceWorkflow.Status.ACTIVE,
            activated_at=timezone.now(),
            archived_at=None,
        )

        self.message_user(
            request,
            f"{updated} workflow(s) activé(s).",
        )

    @admin.action(description="Suspendre les workflows sélectionnés")
    def suspend_workflows(self, request, queryset):
        updated = queryset.update(
            status=GovernanceWorkflow.Status.SUSPENDED,
            is_default=False,
        )

        self.message_user(
            request,
            f"{updated} workflow(s) suspendu(s).",
        )

    @admin.action(description="Archiver les workflows sélectionnés")
    def archive_workflows(self, request, queryset):
        updated = queryset.update(
            status=GovernanceWorkflow.Status.ARCHIVED,
            archived_at=timezone.now(),
            is_default=False,
        )

        self.message_user(
            request,
            f"{updated} workflow(s) archivé(s).",
        )

    @admin.action(description="Définir comme workflow par défaut")
    def set_as_default(self, request, queryset):
        selected = queryset.first()

        if queryset.count() != 1:
            self.message_user(
                request,
                (
                    "Sélectionnez exactement un workflow pour le définir "
                    "comme workflow par défaut."
                ),
                level="ERROR",
            )
            return

        if selected.status != GovernanceWorkflow.Status.ACTIVE:
            self.message_user(
                request,
                (
                    "Le workflow doit être actif avant de devenir "
                    "le workflow par défaut."
                ),
                level="ERROR",
            )
            return

        GovernanceWorkflow.objects.exclude(
            pk=selected.pk,
        ).update(
            is_default=False,
        )

        selected.is_default = True
        selected.save(
            update_fields=[
                "is_default",
                "updated_at",
            ]
        )

        self.message_user(
            request,
            f"Le workflow « {selected.name} » est maintenant par défaut.",
        )


# ==========================================================
# ÉTAPES
# ==========================================================

@admin.register(GovernanceStage)
class GovernanceStageAdmin(admin.ModelAdmin):
    list_display = (
        "workflow",
        "order",
        "code",
        "name",
        "stage_type",
        "responsible_group",
        "duration_display",
        "initial_display",
        "final_display",
        "mandatory_display",
        "active_display",
    )

    list_filter = (
        "workflow",
        "stage_type",
        "is_initial",
        "is_final",
        "is_active",
        "is_mandatory",
        "requires_decision",
        "requires_document",
    )

    search_fields = (
        "code",
        "name",
        "description",
        "instructions",
        "workflow__code",
        "workflow__name",
        "responsible_group__name",
    )

    autocomplete_fields = (
        "workflow",
        "responsible_group",
    )

    readonly_fields = (
        "outgoing_transition_count",
        "incoming_transition_count",
        "task_count",
        "created_at",
        "updated_at",
    )

    ordering = (
        "workflow",
        "order",
    )

    list_select_related = (
        "workflow",
        "responsible_group",
    )

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "workflow",
                    "code",
                    "name",
                    "description",
                    "stage_type",
                    "order",
                )
            },
        ),
        (
            "Position dans le workflow",
            {
                "fields": (
                    "is_initial",
                    "is_final",
                    "is_active",
                    "is_mandatory",
                )
            },
        ),
        (
            "Exigences",
            {
                "fields": (
                    "requires_decision",
                    "requires_comment",
                    "requires_document",
                    "responsible_group",
                    "instructions",
                )
            },
        ),
        (
            "Délais",
            {
                "fields": (
                    "target_duration_days",
                    "escalation_after_days",
                )
            },
        ),
        (
            "Statistiques",
            {
                "fields": (
                    "outgoing_transition_count",
                    "incoming_transition_count",
                    "task_count",
                )
            },
        ),
        (
            "Traçabilité",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    @admin.display(description="Délai")
    def duration_display(self, obj):
        return f"{obj.target_duration_days} jour(s)"

    @admin.display(description="Initiale", boolean=True)
    def initial_display(self, obj):
        return obj.is_initial

    @admin.display(description="Finale", boolean=True)
    def final_display(self, obj):
        return obj.is_final

    @admin.display(description="Obligatoire", boolean=True)
    def mandatory_display(self, obj):
        return obj.is_mandatory

    @admin.display(description="Active", boolean=True)
    def active_display(self, obj):
        return obj.is_active

    @admin.display(description="Transitions sortantes")
    def outgoing_transition_count(self, obj):
        if not obj.pk:
            return 0

        return obj.outgoing_transitions.count()

    @admin.display(description="Transitions entrantes")
    def incoming_transition_count(self, obj):
        if not obj.pk:
            return 0

        return obj.incoming_transitions.count()

    @admin.display(description="Tâches")
    def task_count(self, obj):
        if not obj.pk:
            return 0

        return obj.tasks.count()


# ==========================================================
# TRANSITIONS
# ==========================================================

@admin.register(GovernanceTransition)
class GovernanceTransitionAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "workflow",
        "from_stage_display",
        "arrow_display",
        "to_stage_display",
        "trigger_display",
        "minimum_score_display",
        "permission_display",
        "active_display",
    )

    list_filter = (
        "workflow",
        "trigger",
        "is_active",
        "requires_comment",
        "requires_document",
    )

    search_fields = (
        "code",
        "name",
        "workflow__code",
        "workflow__name",
        "from_stage__code",
        "from_stage__name",
        "to_stage__code",
        "to_stage__name",
        "requires_permission",
        "condition_description",
    )

    autocomplete_fields = (
        "workflow",
        "from_stage",
        "to_stage",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "workflow",
        "from_stage__order",
        "to_stage__order",
    )

    list_select_related = (
        "workflow",
        "from_stage",
        "to_stage",
    )

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "workflow",
                    "code",
                    "name",
                    "trigger",
                    "is_active",
                )
            },
        ),
        (
            "Étapes",
            {
                "fields": (
                    "from_stage",
                    "to_stage",
                )
            },
        ),
        (
            "Conditions",
            {
                "fields": (
                    "requires_comment",
                    "requires_document",
                    "requires_permission",
                    "minimum_score",
                    "condition_description",
                )
            },
        ),
        (
            "Traçabilité",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    @admin.display(description="Étape de départ")
    def from_stage_display(self, obj):
        return obj.from_stage.name

    @admin.display(description="")
    def arrow_display(self, obj):
        return format_html(
            '<strong style="font-size:18px;color:#0d6efd;">→</strong>'
        )

    @admin.display(description="Étape d'arrivée")
    def to_stage_display(self, obj):
        return obj.to_stage.name

    @admin.display(description="Action")
    def trigger_display(self, obj):
        colors = {
            obj.Trigger.APPROVE: "#198754",
            obj.Trigger.REJECT: "#dc3545",
            obj.Trigger.REQUEST_INFO: "#fd7e14",
            obj.Trigger.RETURN: "#6f42c1",
            obj.Trigger.SUBMIT: "#0d6efd",
            obj.Trigger.COMPLETE: "#198754",
            obj.Trigger.SUSPEND: "#dc3545",
            obj.Trigger.RESUME: "#0d6efd",
            obj.Trigger.AUTOMATIC: "#20c997",
            obj.Trigger.CANCEL: "#6c757d",
        }

        return status_badge(
            obj.get_trigger_display(),
            colors.get(obj.trigger, "#6c757d"),
        )

    @admin.display(description="Score minimal")
    def minimum_score_display(self, obj):
        if obj.minimum_score is None:
            return "Aucun"

        return percentage_badge(obj.minimum_score)

    @admin.display(description="Permission")
    def permission_display(self, obj):
        return obj.requires_permission or "Aucune"

    @admin.display(description="Active", boolean=True)
    def active_display(self, obj):
        return obj.is_active


# ==========================================================
# INSTANCES DE GOUVERNANCE
# ==========================================================

@admin.register(GovernanceInstance)
class GovernanceInstanceAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "project",
        "workflow",
        "current_stage",
        "status_display",
        "governance_score_display",
        "open_tasks_display",
        "due_at",
        "overdue_display",
        "last_action_by",
    )

    list_filter = (
        "status",
        "workflow",
        "current_stage",
        "project__postal_office__region",
        "project__postal_office",
        "started_at",
        "due_at",
    )

    search_fields = (
        "reference",
        "project__reference",
        "project__title",
        "project__group__nom",
        "workflow__code",
        "workflow__name",
        "current_stage__code",
        "current_stage__name",
        "started_by__nom",
        "started_by__phone",
        "last_action_by__nom",
        "last_action_by__phone",
    )

    autocomplete_fields = (
        "project",
        "workflow",
        "current_stage",
        "previous_stage",
        "started_by",
        "last_action_by",
    )

    readonly_fields = (
        "reference",
        "overdue_detail",
        "open_tasks_detail",
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )

    date_hierarchy = "created_at"

    save_on_top = True

    list_select_related = (
        "project",
        "workflow",
        "current_stage",
        "previous_stage",
        "started_by",
        "last_action_by",
    )

    inlines = (
        GovernanceTaskInline,
    )

    fieldsets = (
        (
            "Dossier",
            {
                "fields": (
                    "reference",
                    "project",
                    "workflow",
                    "status",
                )
            },
        ),
        (
            "Progression",
            {
                "fields": (
                    "previous_stage",
                    "current_stage",
                    "governance_score",
                    "open_tasks_detail",
                    "overdue_detail",
                )
            },
        ),
        (
            "Délais",
            {
                "fields": (
                    "started_at",
                    "stage_started_at",
                    "due_at",
                    "completed_at",
                )
            },
        ),
        (
            "Suspension ou rejet",
            {
                "fields": (
                    "suspended_at",
                    "suspension_reason",
                    "rejection_reason",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
        (
            "Traçabilité",
            {
                "fields": (
                    "started_by",
                    "last_action_by",
                    "last_action_at",
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    actions = (
        "mark_as_active",
        "mark_as_waiting",
        "mark_as_suspended",
        "mark_as_completed",
        "recalculate_due_date",
    )

    @admin.display(description="Statut")
    def status_display(self, obj):
        colors = {
            obj.Status.NOT_STARTED: "#6c757d",
            obj.Status.ACTIVE: "#0d6efd",
            obj.Status.WAITING: "#fd7e14",
            obj.Status.SUSPENDED: "#dc3545",
            obj.Status.APPROVED: "#198754",
            obj.Status.REJECTED: "#dc3545",
            obj.Status.COMPLETED: "#198754",
            obj.Status.CANCELLED: "#6c757d",
        }

        return status_badge(
            obj.get_status_display(),
            colors.get(obj.status, "#6c757d"),
        )

    @admin.display(description="Score")
    def governance_score_display(self, obj):
        return percentage_badge(obj.governance_score)

    @admin.display(description="Tâches ouvertes")
    def open_tasks_display(self, obj):
        count = obj.open_tasks_count

        if count == 0:
            return status_badge("0", "#198754")

        return status_badge(str(count), "#fd7e14")

    @admin.display(description="Tâches ouvertes")
    def open_tasks_detail(self, obj):
        if not obj.pk:
            return 0

        return obj.open_tasks_count

    @admin.display(description="En retard", boolean=True)
    def overdue_display(self, obj):
        return obj.is_overdue

    @admin.display(description="Situation du délai")
    def overdue_detail(self, obj):
        if not obj.due_at:
            return "Aucune échéance définie"

        if obj.is_overdue:
            return status_badge(
                f"En retard depuis le {obj.due_at:%d/%m/%Y %H:%M}",
                "#dc3545",
            )

        return status_badge(
            f"Échéance : {obj.due_at:%d/%m/%Y %H:%M}",
            "#198754",
        )

    @admin.action(description="Démarrer ou reprendre les instances")
    def mark_as_active(self, request, queryset):
        updated = queryset.update(
            status=GovernanceInstance.Status.ACTIVE,
            started_at=timezone.now(),
            suspended_at=None,
            suspension_reason="",
            last_action_by=request.user,
            last_action_at=timezone.now(),
        )

        self.message_user(
            request,
            f"{updated} instance(s) démarrée(s) ou reprise(s).",
        )

    @admin.action(description="Mettre les instances en attente")
    def mark_as_waiting(self, request, queryset):
        updated = queryset.update(
            status=GovernanceInstance.Status.WAITING,
            last_action_by=request.user,
            last_action_at=timezone.now(),
        )

        self.message_user(
            request,
            f"{updated} instance(s) mise(s) en attente.",
        )

    @admin.action(description="Suspendre les instances sélectionnées")
    def mark_as_suspended(self, request, queryset):
        updated = queryset.update(
            status=GovernanceInstance.Status.SUSPENDED,
            suspended_at=timezone.now(),
            last_action_by=request.user,
            last_action_at=timezone.now(),
        )

        self.message_user(
            request,
            (
                f"{updated} instance(s) suspendue(s). "
                "Ajoutez ensuite le motif de suspension dans chaque dossier."
            ),
        )

    @admin.action(description="Marquer les instances comme terminées")
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(
            status=GovernanceInstance.Status.COMPLETED,
            completed_at=timezone.now(),
            last_action_by=request.user,
            last_action_at=timezone.now(),
        )

        self.message_user(
            request,
            f"{updated} instance(s) terminée(s).",
        )

    @admin.action(description="Recalculer l'échéance de l'étape actuelle")
    def recalculate_due_date(self, request, queryset):
        updated = 0

        for instance in queryset.select_related("current_stage"):
            if not instance.current_stage:
                continue

            start = (
                instance.stage_started_at
                or timezone.now()
            )

            instance.due_at = (
                start
                + timezone.timedelta(
                    days=instance.current_stage.target_duration_days,
                )
            )

            instance.save(
                update_fields=[
                    "due_at",
                    "updated_at",
                ]
            )

            updated += 1

        self.message_user(
            request,
            f"{updated} échéance(s) recalculée(s).",
        )


# ==========================================================
# TÂCHES DE GOUVERNANCE
# ==========================================================

@admin.register(GovernanceTask)
class GovernanceTaskAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "title",
        "instance",
        "stage",
        "task_type",
        "priority_display",
        "status_display",
        "assignment_display",
        "due_at",
        "overdue_display",
    )

    list_filter = (
        "status",
        "priority",
        "task_type",
        "stage__workflow",
        "stage",
        "assigned_group",
        "is_mandatory",
        "due_at",
        "created_at",
    )

    search_fields = (
        "reference",
        "title",
        "description",
        "completion_comment",
        "instance__reference",
        "instance__project__reference",
        "instance__project__title",
        "stage__code",
        "stage__name",
        "assigned_to__nom",
        "assigned_to__phone",
        "assigned_group__name",
    )

    autocomplete_fields = (
        "instance",
        "stage",
        "assigned_to",
        "assigned_group",
        "assigned_by",
        "completed_by",
    )

    readonly_fields = (
        "reference",
        "overdue_detail",
        "created_at",
        "updated_at",
    )

    ordering = (
        "due_at",
        "-priority",
        "created_at",
    )

    date_hierarchy = "created_at"

    save_on_top = True

    list_select_related = (
        "instance",
        "instance__project",
        "stage",
        "assigned_to",
        "assigned_group",
        "assigned_by",
        "completed_by",
    )

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "reference",
                    "instance",
                    "stage",
                    "title",
                    "description",
                    "task_type",
                    "priority",
                    "is_mandatory",
                )
            },
        ),
        (
            "Affectation",
            {
                "fields": (
                    "assigned_to",
                    "assigned_group",
                    "assigned_by",
                    "assigned_at",
                )
            },
        ),
        (
            "Traitement",
            {
                "fields": (
                    "status",
                    "started_at",
                    "due_at",
                    "completed_at",
                    "completed_by",
                    "completion_comment",
                    "result_data",
                    "overdue_detail",
                )
            },
        ),
        (
            "Traçabilité",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    actions = (
        "assign_to_current_user",
        "mark_as_in_progress",
        "mark_as_waiting",
        "mark_as_completed",
        "cancel_tasks",
    )

    @admin.display(description="Priorité")
    def priority_display(self, obj):
        colors = {
            obj.Priority.LOW: "#6c757d",
            obj.Priority.NORMAL: "#0d6efd",
            obj.Priority.HIGH: "#fd7e14",
            obj.Priority.URGENT: "#dc3545",
            obj.Priority.CRITICAL: "#842029",
        }

        return status_badge(
            obj.get_priority_display(),
            colors.get(obj.priority, "#6c757d"),
        )

    @admin.display(description="Statut")
    def status_display(self, obj):
        colors = {
            obj.Status.PENDING: "#6c757d",
            obj.Status.ASSIGNED: "#0d6efd",
            obj.Status.IN_PROGRESS: "#20c997",
            obj.Status.WAITING: "#fd7e14",
            obj.Status.COMPLETED: "#198754",
            obj.Status.REJECTED: "#dc3545",
            obj.Status.CANCELLED: "#6c757d",
        }

        return status_badge(
            obj.get_status_display(),
            colors.get(obj.status, "#6c757d"),
        )

    @admin.display(description="Affectation")
    def assignment_display(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.nom or obj.assigned_to.phone

        if obj.assigned_group:
            return f"Groupe : {obj.assigned_group.name}"

        return "Non assignée"

    @admin.display(description="En retard", boolean=True)
    def overdue_display(self, obj):
        return obj.is_overdue

    @admin.display(description="Situation du délai")
    def overdue_detail(self, obj):
        if not obj.due_at:
            return "Aucune échéance définie"

        if obj.is_overdue:
            return status_badge(
                f"En retard depuis le {obj.due_at:%d/%m/%Y %H:%M}",
                "#dc3545",
            )

        return status_badge(
            f"Échéance : {obj.due_at:%d/%m/%Y %H:%M}",
            "#198754",
        )

    @admin.action(description="M'assigner les tâches sélectionnées")
    def assign_to_current_user(self, request, queryset):
        updated = queryset.update(
            assigned_to=request.user,
            assigned_by=request.user,
            assigned_at=timezone.now(),
            status=GovernanceTask.Status.ASSIGNED,
        )

        self.message_user(
            request,
            f"{updated} tâche(s) assignée(s) à votre compte.",
        )

    @admin.action(description="Marquer comme en cours")
    def mark_as_in_progress(self, request, queryset):
        updated = queryset.update(
            status=GovernanceTask.Status.IN_PROGRESS,
            started_at=timezone.now(),
        )

        self.message_user(
            request,
            f"{updated} tâche(s) marquée(s) comme en cours.",
        )

    @admin.action(description="Mettre en attente")
    def mark_as_waiting(self, request, queryset):
        updated = queryset.update(
            status=GovernanceTask.Status.WAITING,
        )

        self.message_user(
            request,
            f"{updated} tâche(s) mise(s) en attente.",
        )

    @admin.action(description="Marquer comme terminée")
    def mark_as_completed(self, request, queryset):
        valid_tasks = queryset.exclude(
            completion_comment="",
        )

        updated = valid_tasks.update(
            status=GovernanceTask.Status.COMPLETED,
            completed_at=timezone.now(),
            completed_by=request.user,
        )

        skipped = queryset.count() - updated

        message = f"{updated} tâche(s) terminée(s)."

        if skipped:
            message += (
                f" {skipped} tâche(s) ignorée(s), car aucun commentaire "
                "de traitement n'était renseigné."
            )

        self.message_user(
            request,
            message,
        )

    @admin.action(description="Annuler les tâches sélectionnées")
    def cancel_tasks(self, request, queryset):
        updated = queryset.update(
            status=GovernanceTask.Status.CANCELLED,
        )

        self.message_user(
            request,
            f"{updated} tâche(s) annulée(s).",
        )


# ==========================================================
# PERSONNALISATION GÉNÉRALE
# ==========================================================

admin.site.site_header = "Administration YAAYESS"
admin.site.site_title = "YAAYESS"
admin.site.index_title = (
    "Pilotage de l'épargne, de l'investissement "
    "et de la gouvernance communautaire"
)

# ==========================================================
# JOURNAL DES DÉCISIONS DE GOUVERNANCE
# ==========================================================

@admin.register(GovernanceDecisionLog)
class GovernanceDecisionLogAdmin(admin.ModelAdmin):
    """
    Administration en lecture seule de la piste d'audit
    du moteur de gouvernance.
    """

    list_display = (
        "reference",
        "project",
        "decision_display",
        "application_status_display",
        "global_score_display",
        "from_stage",
        "to_stage",
        "actor",
        "evaluated_at",
    )

    list_filter = (
        "decision_code",
        "application_status",
        "eligible",
        "can_advance",
        "workflow",
        "from_stage",
        "to_stage",
        "evaluated_at",
    )

    search_fields = (
        "reference",
        "instance__reference",
        "project__reference",
        "project__title",
        "workflow__code",
        "workflow__name",
        "summary",
        "actor__nom",
        "actor__phone",
        "actor__email",
        "actor_ip_address",
    )

    readonly_fields = (
        "reference",
        "decision_display_detail",
        "application_status_display_detail",
        "global_score_display_detail",
        "instance",
        "project",
        "workflow",
        "from_stage",
        "to_stage",
        "transition",
        "eligible",
        "can_advance",
        "summary",
        "formatted_criteria_snapshot",
        "formatted_blocking_reasons",
        "formatted_warnings",
        "formatted_engine_snapshot",
        "actor",
        "evaluated_at",
        "applied_at",
        "override_reason",
        "failure_message",
        "actor_ip_address",
        "actor_user_agent",
        "created_at",
        "updated_at",
    )

    ordering = (
        "-evaluated_at",
        "-created_at",
    )

    date_hierarchy = "evaluated_at"

    list_select_related = (
        "instance",
        "project",
        "workflow",
        "from_stage",
        "to_stage",
        "transition",
        "actor",
    )

    fieldsets = (
        (
            "Décision",
            {
                "fields": (
                    "reference",
                    "decision_display_detail",
                    "application_status_display_detail",
                    "global_score_display_detail",
                    "eligible",
                    "can_advance",
                    "summary",
                )
            },
        ),
        (
            "Dossier concerné",
            {
                "fields": (
                    "instance",
                    "project",
                    "workflow",
                )
            },
        ),
        (
            "Transition",
            {
                "fields": (
                    "from_stage",
                    "to_stage",
                    "transition",
                )
            },
        ),
        (
            "Résultat détaillé du moteur",
            {
                "fields": (
                    "formatted_criteria_snapshot",
                    "formatted_blocking_reasons",
                    "formatted_warnings",
                )
            },
        ),
        (
            "Instantané technique",
            {
                "fields": (
                    "formatted_engine_snapshot",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
        (
            "Acteur et sécurité",
            {
                "fields": (
                    "actor",
                    "evaluated_at",
                    "applied_at",
                    "actor_ip_address",
                    "actor_user_agent",
                )
            },
        ),
        (
            "Remplacement manuel ou échec",
            {
                "fields": (
                    "override_reason",
                    "failure_message",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
        (
            "Traçabilité technique",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    actions = None

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "instance",
                "project",
                "workflow",
                "from_stage",
                "to_stage",
                "transition",
                "actor",
            )
        )

    # ======================================================
    # SÉCURITÉ : JOURNAL STRICTEMENT EN LECTURE SEULE
    # ======================================================

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        """
        Autorise l'ouverture de la fiche dans l'administration,
        mais tous les champs restent en lecture seule.
        """
        return request.user.has_perm(
            "governance.view_governancedecisionlog"
        )

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.has_perm(
                "governance.view_governancedecisionlog"
            )
            or request.user.has_perm(
                "governance.view_governance_audit_log"
            )
        )

    def get_actions(self, request):
        """
        Supprime toutes les actions groupées, y compris
        l'action native de suppression.
        """
        return {}

    # ======================================================
    # AFFICHAGE DES BADGES
    # ======================================================

    @admin.display(description="Décision")
    def decision_display(self, obj):
        colors = {
            obj.DecisionCode.APPROVE: "#198754",
            obj.DecisionCode.ADVANCE: "#0d6efd",
            obj.DecisionCode.REQUEST_INFO: "#fd7e14",
            obj.DecisionCode.MANUAL_REVIEW: "#6f42c1",
            obj.DecisionCode.BLOCK: "#dc3545",
            obj.DecisionCode.REJECT: "#842029",
        }

        return status_badge(
            obj.get_decision_code_display(),
            colors.get(
                obj.decision_code,
                "#6c757d",
            ),
        )

    @admin.display(description="Statut d'application")
    def application_status_display(self, obj):
        colors = {
            obj.ApplicationStatus.RECOMMENDED: "#6f42c1",
            obj.ApplicationStatus.APPLIED: "#198754",
            obj.ApplicationStatus.NOT_APPLIED: "#fd7e14",
            obj.ApplicationStatus.OVERRIDDEN: "#0d6efd",
            obj.ApplicationStatus.FAILED: "#dc3545",
        }

        return status_badge(
            obj.get_application_status_display(),
            colors.get(
                obj.application_status,
                "#6c757d",
            ),
        )

    @admin.display(description="Score")
    def global_score_display(self, obj):
        return percentage_badge(
            obj.global_score
        )

    @admin.display(description="Décision")
    def decision_display_detail(self, obj):
        return self.decision_display(obj)

    @admin.display(description="Statut d'application")
    def application_status_display_detail(self, obj):
        return self.application_status_display(obj)

    @admin.display(description="Score global")
    def global_score_display_detail(self, obj):
        return self.global_score_display(obj)

    # ======================================================
    # FORMATAGE DES DONNÉES JSON
    # ======================================================

    @staticmethod
    def _json_block(value, empty_message="Aucune donnée"):
        if value in (None, "", [], {}):
            return format_html(
                '<span style="color:#6c757d;">{}</span>',
                empty_message,
            )

        try:
            formatted = json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        except (TypeError, ValueError):
            formatted = str(value)

        return format_html(
            (
                '<pre style="'
                'white-space:pre-wrap;'
                'word-break:break-word;'
                'max-height:520px;'
                'overflow:auto;'
                'padding:14px;'
                'border:1px solid #dee2e6;'
                'border-radius:8px;'
                'background:#f8f9fa;'
                'font-size:12px;'
                'line-height:1.5;'
                '">{}</pre>'
            ),
            formatted,
        )

    @admin.display(description="Critères évalués")
    def formatted_criteria_snapshot(self, obj):
        return self._json_block(
            obj.criteria_snapshot,
            "Aucun critère enregistré",
        )

    @admin.display(description="Motifs bloquants")
    def formatted_blocking_reasons(self, obj):
        if not obj.blocking_reasons:
            return status_badge(
                "Aucun blocage",
                "#198754",
            )

        items = "".join(
            f"<li>{reason}</li>"
            for reason in obj.blocking_reasons
        )

        return format_html(
            (
                '<div style="'
                'padding:12px;'
                'border-left:4px solid #dc3545;'
                'background:#f8d7da;'
                'border-radius:5px;'
                'color:#842029;'
                '">'
                "<strong>Blocages détectés</strong>"
                "<ul style='margin:8px 0 0 18px;'>{}</ul>"
                "</div>"
            ),
            format_html(items),
        )

    @admin.display(description="Avertissements")
    def formatted_warnings(self, obj):
        if not obj.warnings:
            return status_badge(
                "Aucun avertissement",
                "#198754",
            )

        items = "".join(
            f"<li>{warning}</li>"
            for warning in obj.warnings
        )

        return format_html(
            (
                '<div style="'
                'padding:12px;'
                'border-left:4px solid #fd7e14;'
                'background:#fff3cd;'
                'border-radius:5px;'
                'color:#664d03;'
                '">'
                "<strong>Avertissements</strong>"
                "<ul style='margin:8px 0 0 18px;'>{}</ul>"
                "</div>"
            ),
            format_html(items),
        )

    @admin.display(description="Instantané complet du moteur")
    def formatted_engine_snapshot(self, obj):
        return self._json_block(
            obj.engine_snapshot,
            "Aucun instantané enregistré",
        )
