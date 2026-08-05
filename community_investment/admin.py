from __future__ import annotations

from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html

from .models import (
    CommunityImpact,
    CommunityInvestmentProject,
    DividendDeclaration,
    DividendEntitlement,
    DividendPayment,
    InvestmentEligibilityPolicy,
    MemberEconomicRight,
    PostalOffice,
    PostalRegion,
    ProfitAllocation,
    ProjectContribution,
    ProjectDocument,
    ProjectExpense,
    ProjectFeeAccrual,
    ProjectFeeRule,
    ProjectFinancialStatement,
    ProjectIncident,
    ProjectLegalEntity,
    ProjectMeeting,
    ProjectMilestone,
    ProjectRevenue,
    ProjectStakeholder,
    ReinvestmentDecision,
    ShareTransaction,
)


# ==========================================================
# OUTILS
# ==========================================================

def format_money(value) -> str:
    """
    Formate un montant en FCFA pour l'administration Django.
    """
    if value is None:
        value = 0

    formatted_value = f"{value:,.0f}".replace(",", " ")

    return f"{formatted_value} FCFA"


def format_percentage(value) -> str:
    """
    Formate un pourcentage.
    """
    if value is None:
        value = 0

    return f"{value:.2f} %"


# ==========================================================
# INLINES — ORGANISATION TERRITORIALE
# ==========================================================

class PostalOfficeInline(admin.TabularInline):
    model = PostalOffice
    extra = 0
    fields = (
        "name",
        "code",
        "city",
        "manager",
        "is_active",
    )
    show_change_link = True


# ==========================================================
# INLINES — PROJET
# ==========================================================

class ProjectLegalEntityInline(admin.StackedInline):
    model = ProjectLegalEntity
    extra = 0
    max_num = 1
    can_delete = True
    show_change_link = True

    fields = (
        "legal_name",
        "legal_form",
        "registration_number",
        "tax_number",
        "registered_office",
        "share_capital",
        "incorporation_date",
        "is_registered",
    )


class ProjectStakeholderInline(admin.TabularInline):
    model = ProjectStakeholder
    extra = 0
    show_change_link = True

    fields = (
        "holder_type",
        "legal_name",
        "ownership_percentage",
        "voting_percentage",
        "status",
    )

    readonly_fields = (
        "legal_name",
    )


class ProjectContributionInline(admin.TabularInline):
    model = ProjectContribution
    extra = 0
    show_change_link = True

    fields = (
        "stakeholder",
        "contribution_type",
        "declared_value",
        "recognized_value",
        "status",
    )


class ProjectFeeRuleInline(admin.TabularInline):
    model = ProjectFeeRule
    extra = 0
    show_change_link = True

    fields = (
        "beneficiary_type",
        "fee_type",
        "calculation_method",
        "fixed_amount",
        "percentage_rate",
        "status",
    )


class ProjectMilestoneInline(admin.TabularInline):
    model = ProjectMilestone
    extra = 0
    show_change_link = True

    fields = (
        "title",
        "planned_end_date",
        "progress_percentage",
        "status",
        "responsible",
    )


class ProjectIncidentInline(admin.TabularInline):
    model = ProjectIncident
    extra = 0
    show_change_link = True

    fields = (
        "title",
        "severity",
        "status",
        "reported_at",
    )

    readonly_fields = (
        "reported_at",
    )


class ProjectDocumentInline(admin.TabularInline):
    model = ProjectDocument
    extra = 0
    show_change_link = True

    fields = (
        "document_type",
        "title",
        "version",
        "is_validated",
        "uploaded_by",
    )


class ProjectRevenueInline(admin.TabularInline):
    model = ProjectRevenue
    extra = 0
    show_change_link = True

    fields = (
        "revenue_date",
        "description",
        "amount",
        "reference",
    )


class ProjectExpenseInline(admin.TabularInline):
    model = ProjectExpense
    extra = 0
    show_change_link = True

    fields = (
        "expense_date",
        "category",
        "description",
        "amount",
        "reference",
    )


# ==========================================================
# ORGANISATION TERRITORIALE
# ==========================================================

@admin.register(PostalRegion)
class PostalRegionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "manager",
        "office_count",
        "active_badge",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "name",
        "code",
        "manager__nom",
        "manager__phone",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "name",
    )

    inlines = (
        PostalOfficeInline,
    )

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "name",
                    "code",
                    "description",
                )
            },
        ),
        (
            "Responsabilité",
            {
                "fields": (
                    "manager",
                    "is_active",
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

    @admin.display(description="Bureaux")
    def office_count(self, obj):
        return obj.postal_offices.count()

    @admin.display(description="Statut")
    def active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="color:#198754;font-weight:700;">● Active</span>'
            )

        return format_html(
            '<span style="color:#dc3545;font-weight:700;">● Inactive</span>'
        )


@admin.register(PostalOffice)
class PostalOfficeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "city",
        "region",
        "manager",
        "authorized_user_count",
        "active_badge",
    )

    list_filter = (
        "region",
        "city",
        "is_active",
    )

    search_fields = (
        "name",
        "code",
        "city",
        "address",
        "phone",
        "email",
        "manager__nom",
        "manager__phone",
    )

    autocomplete_fields = (
        "region",
        "manager",
        "authorized_users",
    )

    filter_horizontal = (
        "authorized_users",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "region__name",
        "name",
    )

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "region",
                    "name",
                    "code",
                    "city",
                    "address",
                )
            },
        ),
        (
            "Coordonnées",
            {
                "fields": (
                    "phone",
                    "email",
                )
            },
        ),
        (
            "Responsabilité et accès",
            {
                "fields": (
                    "manager",
                    "authorized_users",
                    "is_active",
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

    @admin.display(description="Utilisateurs")
    def authorized_user_count(self, obj):
        return obj.authorized_users.count()

    @admin.display(description="Statut")
    def active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="color:#198754;font-weight:700;">● Actif</span>'
            )

        return format_html(
            '<span style="color:#dc3545;font-weight:700;">● Inactif</span>'
        )


# ==========================================================
# POLITIQUE D'ÉLIGIBILITÉ
# ==========================================================

@admin.register(InvestmentEligibilityPolicy)
class InvestmentEligibilityPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "minimum_capital_display",
        "minimum_group_equity_rate",
        "suggested_poste_equity_rate",
        "suggested_yaayess_equity_rate",
        "effective_from",
        "effective_until",
        "active_badge",
    )

    list_filter = (
        "is_active",
        "requires_general_assembly_resolution",
        "requires_business_plan",
        "requires_feasibility_study",
        "requires_verified_financial_statements",
        "effective_from",
    )

    search_fields = (
        "name",
        "notes",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "name",
                    "is_active",
                    "notes",
                )
            },
        ),
        (
            "Conditions financières",
            {
                "fields": (
                    "minimum_capital",
                    "minimum_internal_reserve_rate",
                    "minimum_group_equity_rate",
                    "suggested_poste_equity_rate",
                    "suggested_yaayess_equity_rate",
                )
            },
        ),
        (
            "Maturité du groupement",
            {
                "fields": (
                    "minimum_group_age_months",
                    "minimum_active_members",
                    "minimum_savings_regularity_rate",
                    "minimum_governance_score",
                )
            },
        ),
        (
            "Documents et validations requis",
            {
                "fields": (
                    "requires_general_assembly_resolution",
                    "requires_business_plan",
                    "requires_feasibility_study",
                    "requires_verified_financial_statements",
                    "requires_environmental_assessment",
                    "requires_conflict_of_interest_declaration",
                    "requires_signed_investment_agreement",
                )
            },
        ),
        (
            "Période d'application",
            {
                "fields": (
                    "effective_from",
                    "effective_until",
                )
            },
        ),
        (
            "Traçabilité",
            {
                "fields": (
                    "created_by",
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    @admin.display(description="Capital minimum")
    def minimum_capital_display(self, obj):
        return format_money(obj.minimum_capital)

    @admin.display(description="Statut")
    def active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="color:#198754;font-weight:700;">● Active</span>'
            )

        return format_html(
            '<span style="color:#6c757d;font-weight:700;">● Inactive</span>'
        )


# ==========================================================
# PROJETS D'INVESTISSEMENT
# ==========================================================

@admin.register(CommunityInvestmentProject)
class CommunityInvestmentProjectAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "title",
        "group",
        "postal_office",
        "sector",
        "total_project_cost_display",
        "capital_completion_display",
        "eligibility_badge",
        "status_badge",
        "risk_badge",
        "progress_percentage",
    )

    list_filter = (
        "status",
        "eligibility_status",
        "risk_level",
        "sector",
        "postal_office__region",
        "postal_office",
        "eligibility_policy",
        "created_at",
    )

    search_fields = (
        "reference",
        "title",
        "description",
        "project_location",
        "group__nom",
        "postal_office__name",
        "postal_office__code",
        "project_lead__nom",
        "project_lead__phone",
    )

    autocomplete_fields = (
        "group",
        "postal_office",
        "eligibility_policy",
        "project_lead",
        "reviewed_by",
        "approved_by",
        "created_by",
    )

    readonly_fields = (
        "reference",
        "threshold_at_submission",
        "recognized_capital_display",
        "remaining_capital_display",
        "capital_completion_display",
        "ownership_total_display",
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"

    ordering = (
        "-created_at",
    )

    save_on_top = True

    list_select_related = (
        "group",
        "postal_office",
        "postal_office__region",
        "eligibility_policy",
        "project_lead",
    )

    inlines = (
        ProjectLegalEntityInline,
        ProjectStakeholderInline,
        ProjectContributionInline,
        ProjectFeeRuleInline,
        ProjectMilestoneInline,
        ProjectIncidentInline,
        ProjectRevenueInline,
        ProjectExpenseInline,
        ProjectDocumentInline,
    )

    fieldsets = (
        (
            "Identification du projet",
            {
                "fields": (
                    "reference",
                    "title",
                    "description",
                    "sector",
                    "project_location",
                )
            },
        ),
        (
            "Porteur et accompagnement",
            {
                "fields": (
                    "group",
                    "postal_office",
                    "project_lead",
                    "eligibility_policy",
                )
            },
        ),
        (
            "Capitalisation",
            {
                "fields": (
                    "capital_at_submission",
                    "threshold_at_submission",
                    "total_project_cost",
                    "group_planned_equity",
                    "recognized_capital_display",
                    "remaining_capital_display",
                    "capital_completion_display",
                    "ownership_total_display",
                )
            },
        ),
        (
            "Évaluation du projet",
            {
                "fields": (
                    "governance_score",
                    "savings_regularity_rate",
                    "expected_return_rate",
                    "risk_level",
                    "eligibility_status",
                    "eligibility_override_reason",
                )
            },
        ),
        (
            "Impact prévisionnel",
            {
                "fields": (
                    "expected_jobs",
                    "expected_beneficiaries",
                )
            },
        ),
        (
            "Décision collective du groupement",
            {
                "fields": (
                    "general_assembly_resolution_reference",
                    "general_assembly_resolution_date",
                )
            },
        ),
        (
            "Calendrier et avancement",
            {
                "fields": (
                    "planned_start_date",
                    "planned_end_date",
                    "actual_start_date",
                    "actual_end_date",
                    "progress_percentage",
                )
            },
        ),
        (
            "Instruction et décision",
            {
                "fields": (
                    "status",
                    "submitted_at",
                    "reviewed_at",
                    "reviewed_by",
                    "decided_at",
                    "approved_by",
                    "rejection_reason",
                )
            },
        ),
        (
            "Notes internes",
            {
                "fields": (
                    "internal_notes",
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
                    "created_by",
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
        "evaluate_eligibility",
        "mark_as_submitted",
        "mark_as_central_review",
        "mark_as_approved",
        "mark_as_suspended",
    )

    @admin.display(description="Coût total")
    def total_project_cost_display(self, obj):
        return format_money(obj.total_project_cost)

    @admin.display(description="Capital reconnu")
    def recognized_capital_display(self, obj):
        return format_money(obj.total_recognized_capital)

    @admin.display(description="Capital restant")
    def remaining_capital_display(self, obj):
        return format_money(obj.remaining_capital_to_raise)

    @admin.display(description="Capitalisation")
    def capital_completion_display(self, obj):
        rate = obj.capital_completion_rate

        if rate >= 100:
            color = "#198754"
        elif rate >= 75:
            color = "#0d6efd"
        elif rate >= 50:
            color = "#fd7e14"
        else:
            color = "#dc3545"

        return format_html(
            '<strong style="color:{};">{:.2f} %</strong>',
            color,
            rate,
        )

    @admin.display(description="Total participation")
    def ownership_total_display(self, obj):
        return format_percentage(
            obj.total_active_ownership_percentage
        )

    @admin.display(description="Éligibilité")
    def eligibility_badge(self, obj):
        colors = {
            obj.EligibilityStatus.PENDING: "#6c757d",
            obj.EligibilityStatus.ELIGIBLE: "#198754",
            obj.EligibilityStatus.NOT_ELIGIBLE: "#dc3545",
            obj.EligibilityStatus.OVERRIDDEN: "#fd7e14",
        }

        color = colors.get(
            obj.eligibility_status,
            "#6c757d",
        )

        return format_html(
            '<span style="color:{};font-weight:700;">● {}</span>',
            color,
            obj.get_eligibility_status_display(),
        )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        success_statuses = {
            obj.Status.ELIGIBLE,
            obj.Status.APPROVED,
            obj.Status.READY_TO_START,
            obj.Status.IN_PROGRESS,
            obj.Status.COMPLETED,
        }

        danger_statuses = {
            obj.Status.NOT_ELIGIBLE,
            obj.Status.REJECTED,
            obj.Status.CANCELLED,
        }

        warning_statuses = {
            obj.Status.ADDITIONAL_INFO,
            obj.Status.SUSPENDED,
        }

        if obj.status in success_statuses:
            color = "#198754"
        elif obj.status in danger_statuses:
            color = "#dc3545"
        elif obj.status in warning_statuses:
            color = "#fd7e14"
        else:
            color = "#0d6efd"

        return format_html(
            '<span style="color:{};font-weight:700;">● {}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Risque")
    def risk_badge(self, obj):
        colors = {
            obj.RiskLevel.LOW: "#198754",
            obj.RiskLevel.MODERATE: "#0d6efd",
            obj.RiskLevel.HIGH: "#fd7e14",
            obj.RiskLevel.CRITICAL: "#dc3545",
        }

        return format_html(
            '<span style="color:{};font-weight:700;">● {}</span>',
            colors.get(obj.risk_level, "#6c757d"),
            obj.get_risk_level_display(),
        )

    @admin.action(description="Évaluer l'éligibilité de base")
    def evaluate_eligibility(self, request, queryset):
        eligible_count = 0
        not_eligible_count = 0

        for project in queryset.select_related(
            "eligibility_policy"
        ):
            if project.evaluate_basic_eligibility():
                eligible_count += 1
            else:
                not_eligible_count += 1

            project.save(
                update_fields=[
                    "eligibility_status",
                    "updated_at",
                ]
            )

        self.message_user(
            request,
            (
                f"{eligible_count} projet(s) éligible(s), "
                f"{not_eligible_count} projet(s) non éligible(s)."
            ),
        )

    @admin.action(description="Marquer comme soumis")
    def mark_as_submitted(self, request, queryset):
        updated = queryset.update(
            status=CommunityInvestmentProject.Status.SUBMITTED,
        )

        self.message_user(
            request,
            f"{updated} projet(s) marqué(s) comme soumis.",
        )

    @admin.action(description="Transmettre à l'instruction centrale")
    def mark_as_central_review(self, request, queryset):
        updated = queryset.update(
            status=CommunityInvestmentProject.Status.CENTRAL_REVIEW,
        )

        self.message_user(
            request,
            f"{updated} projet(s) transmis à l'instruction centrale.",
        )

    @admin.action(description="Marquer comme approuvé")
    def mark_as_approved(self, request, queryset):
        updated = queryset.update(
            status=CommunityInvestmentProject.Status.APPROVED,
            approved_by=request.user,
        )

        self.message_user(
            request,
            f"{updated} projet(s) approuvé(s).",
        )

    @admin.action(description="Suspendre les projets sélectionnés")
    def mark_as_suspended(self, request, queryset):
        updated = queryset.update(
            status=CommunityInvestmentProject.Status.SUSPENDED,
        )

        self.message_user(
            request,
            f"{updated} projet(s) suspendu(s).",
        )


# ==========================================================
# ENTITÉ JURIDIQUE
# ==========================================================

@admin.register(ProjectLegalEntity)
class ProjectLegalEntityAdmin(admin.ModelAdmin):
    list_display = (
        "legal_name",
        "project",
        "legal_form",
        "registration_number",
        "share_capital_display",
        "is_registered",
    )

    list_filter = (
        "legal_form",
        "is_registered",
        "incorporation_date",
    )

    search_fields = (
        "legal_name",
        "registration_number",
        "tax_number",
        "project__reference",
        "project__title",
    )

    autocomplete_fields = (
        "project",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Capital social")
    def share_capital_display(self, obj):
        return format_money(obj.share_capital)


# ==========================================================
# ASSOCIÉS ET ACTIONNAIRES
# ==========================================================

@admin.register(ProjectStakeholder)
class ProjectStakeholderAdmin(admin.ModelAdmin):
    list_display = (
        "legal_name",
        "project",
        "holder_type",
        "recognized_contribution_display",
        "ownership_percentage",
        "voting_percentage",
        "status_badge",
    )

    list_filter = (
        "holder_type",
        "status",
        "project__postal_office__region",
    )

    search_fields = (
        "legal_name",
        "project__reference",
        "project__title",
        "group__nom",
        "user__nom",
        "user__phone",
        "investment_agreement_reference",
    )

    autocomplete_fields = (
        "project",
        "group",
        "user",
        "approved_by",
    )

    readonly_fields = (
        "legal_name",
        "recognized_contribution_display",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Projet et détenteur",
            {
                "fields": (
                    "project",
                    "holder_type",
                    "group",
                    "user",
                    "legal_name",
                )
            },
        ),
        (
            "Participation",
            {
                "fields": (
                    "shares_count",
                    "ownership_percentage",
                    "voting_percentage",
                    "recognized_contribution_display",
                    "status",
                )
            },
        ),
        (
            "Validation contractuelle",
            {
                "fields": (
                    "investment_agreement_reference",
                    "approved_at",
                    "approved_by",
                )
            },
        ),
        (
            "Informations complémentaires",
            {
                "fields": (
                    "notes",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Apports reconnus")
    def recognized_contribution_display(self, obj):
        return format_money(
            obj.recognized_contribution_value
        )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            obj.Status.PROPOSED: "#6c757d",
            obj.Status.APPROVED: "#0d6efd",
            obj.Status.ACTIVE: "#198754",
            obj.Status.SUSPENDED: "#fd7e14",
            obj.Status.EXITED: "#dc3545",
        }

        return format_html(
            '<span style="color:{};font-weight:700;">● {}</span>',
            colors.get(obj.status, "#6c757d"),
            obj.get_status_display(),
        )


@admin.register(ProjectContribution)
class ProjectContributionAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "stakeholder",
        "contribution_type",
        "declared_value_display",
        "recognized_value_display",
        "status_badge",
        "contribution_date",
    )

    list_filter = (
        "contribution_type",
        "status",
        "project__postal_office__region",
        "contribution_date",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "stakeholder__legal_name",
        "description",
        "valuation_report_reference",
    )

    autocomplete_fields = (
        "project",
        "stakeholder",
        "validated_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    actions = (
        "recognize_selected_contributions",
        "reject_selected_contributions",
    )

    @admin.display(description="Valeur déclarée")
    def declared_value_display(self, obj):
        return format_money(obj.declared_value)

    @admin.display(description="Valeur reconnue")
    def recognized_value_display(self, obj):
        return format_money(obj.recognized_value)

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            obj.Status.PROPOSED: "#6c757d",
            obj.Status.UNDER_VALUATION: "#0d6efd",
            obj.Status.RECOGNIZED: "#198754",
            obj.Status.REJECTED: "#dc3545",
            obj.Status.CANCELLED: "#6c757d",
        }

        return format_html(
            '<span style="color:{};font-weight:700;">● {}</span>',
            colors.get(obj.status, "#6c757d"),
            obj.get_status_display(),
        )

    @admin.action(description="Reconnaître les apports sélectionnés")
    def recognize_selected_contributions(self, request, queryset):
        updated = queryset.filter(
            recognized_value__gt=0,
        ).update(
            status=ProjectContribution.Status.RECOGNIZED,
            validated_by=request.user,
        )

        self.message_user(
            request,
            f"{updated} apport(s) reconnu(s).",
        )

    @admin.action(description="Rejeter les apports sélectionnés")
    def reject_selected_contributions(self, request, queryset):
        updated = queryset.update(
            status=ProjectContribution.Status.REJECTED,
            validated_by=request.user,
        )

        self.message_user(
            request,
            f"{updated} apport(s) rejeté(s).",
        )


@admin.register(MemberEconomicRight)
class MemberEconomicRightAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "project_display",
        "stakeholder",
        "contribution_reference_display",
        "economic_percentage",
        "dividend_percentage",
        "is_active",
    )

    list_filter = (
        "is_active",
        "effective_from",
        "stakeholder__project__postal_office__region",
    )

    search_fields = (
        "member__alias",
        "member__user__nom",
        "member__user__phone",
        "stakeholder__project__reference",
        "stakeholder__project__title",
    )

    autocomplete_fields = (
        "stakeholder",
        "member",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Projet")
    def project_display(self, obj):
        return obj.stakeholder.project

    @admin.display(description="Contribution")
    def contribution_reference_display(self, obj):
        return format_money(
            obj.contribution_reference_amount
        )


@admin.register(ShareTransaction)
class ShareTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "transaction_type",
        "from_stakeholder",
        "to_stakeholder",
        "shares_count",
        "transaction_amount_display",
        "transaction_date",
    )

    list_filter = (
        "transaction_type",
        "transaction_date",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "from_stakeholder__legal_name",
        "to_stakeholder__legal_name",
        "resolution_reference",
    )

    autocomplete_fields = (
        "project",
        "from_stakeholder",
        "to_stakeholder",
        "approved_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Montant")
    def transaction_amount_display(self, obj):
        return format_money(obj.transaction_amount)


# ==========================================================
# FRAIS ET MODÈLE ÉCONOMIQUE
# ==========================================================

@admin.register(ProjectFeeRule)
class ProjectFeeRuleAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "beneficiary_name",
        "fee_type",
        "calculation_method",
        "rate_or_amount_display",
        "annual_cap_display",
        "status_badge",
    )

    list_filter = (
        "beneficiary_type",
        "fee_type",
        "calculation_method",
        "status",
        "effective_from",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "beneficiary_name",
        "agreement_reference",
    )

    autocomplete_fields = (
        "project",
        "approved_by",
    )

    readonly_fields = (
        "beneficiary_name",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Montant ou taux")
    def rate_or_amount_display(self, obj):
        if (
            obj.calculation_method
            == obj.CalculationMethod.FIXED
        ):
            return format_money(obj.fixed_amount)

        return format_percentage(obj.percentage_rate)

    @admin.display(description="Plafond annuel")
    def annual_cap_display(self, obj):
        if obj.annual_cap is None:
            return "Non plafonné"

        return format_money(obj.annual_cap)

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            obj.Status.DRAFT: "#6c757d",
            obj.Status.APPROVED: "#0d6efd",
            obj.Status.ACTIVE: "#198754",
            obj.Status.SUSPENDED: "#fd7e14",
            obj.Status.TERMINATED: "#dc3545",
        }

        return format_html(
            '<span style="color:{};font-weight:700;">● {}</span>',
            colors.get(obj.status, "#6c757d"),
            obj.get_status_display(),
        )


@admin.register(ProjectFeeAccrual)
class ProjectFeeAccrualAdmin(admin.ModelAdmin):
    list_display = (
        "fee_rule",
        "period_start",
        "period_end",
        "calculation_base_display",
        "calculated_amount_display",
        "status",
        "paid_at",
    )

    list_filter = (
        "status",
        "period_start",
        "period_end",
        "fee_rule__beneficiary_type",
        "fee_rule__fee_type",
    )

    search_fields = (
        "fee_rule__project__reference",
        "fee_rule__project__title",
        "fee_rule__beneficiary_name",
        "payment_reference",
    )

    autocomplete_fields = (
        "fee_rule",
        "approved_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Base de calcul")
    def calculation_base_display(self, obj):
        return format_money(obj.calculation_base)

    @admin.display(description="Montant calculé")
    def calculated_amount_display(self, obj):
        return format_money(obj.calculated_amount)


# ==========================================================
# GESTION FINANCIÈRE
# ==========================================================

@admin.register(ProjectRevenue)
class ProjectRevenueAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "revenue_date",
        "description",
        "amount_display",
        "reference",
        "recorded_by",
    )

    list_filter = (
        "revenue_date",
        "project__sector",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "description",
        "reference",
    )

    autocomplete_fields = (
        "project",
        "recorded_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    date_hierarchy = "revenue_date"

    @admin.display(description="Montant")
    def amount_display(self, obj):
        return format_money(obj.amount)


@admin.register(ProjectExpense)
class ProjectExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "expense_date",
        "category",
        "description",
        "amount_display",
        "reference",
        "validated_by",
    )

    list_filter = (
        "category",
        "expense_date",
        "project__sector",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "description",
        "reference",
    )

    autocomplete_fields = (
        "project",
        "validated_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    date_hierarchy = "expense_date"

    @admin.display(description="Montant")
    def amount_display(self, obj):
        return format_money(obj.amount)


@admin.register(ProjectFinancialStatement)
class ProjectFinancialStatementAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "period_start",
        "period_end",
        "turnover_display",
        "net_profit_display",
        "roi_display",
        "status",
    )

    list_filter = (
        "status",
        "period_start",
        "period_end",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "notes",
    )

    autocomplete_fields = (
        "project",
        "verified_by",
    )

    readonly_fields = (
        "roi_display",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Projet et période",
            {
                "fields": (
                    "project",
                    "period_start",
                    "period_end",
                    "status",
                )
            },
        ),
        (
            "Compte de résultat",
            {
                "fields": (
                    "turnover",
                    "operating_expenses",
                    "taxes",
                    "depreciation",
                    "management_fees",
                    "net_profit",
                )
            },
        ),
        (
            "Situation financière",
            {
                "fields": (
                    "total_assets",
                    "total_liabilities",
                    "cash_balance",
                    "roi_display",
                )
            },
        ),
        (
            "Validation",
            {
                "fields": (
                    "verified_by",
                    "approved_at",
                    "notes",
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

    @admin.display(description="Chiffre d'affaires")
    def turnover_display(self, obj):
        return format_money(obj.turnover)

    @admin.display(description="Résultat net")
    def net_profit_display(self, obj):
        color = "#198754" if obj.net_profit >= 0 else "#dc3545"

        return format_html(
            '<strong style="color:{};">{}</strong>',
            color,
            format_money(obj.net_profit),
        )

    @admin.display(description="ROI")
    def roi_display(self, obj):
        return format_percentage(
            obj.return_on_investment
        )


@admin.register(ProfitAllocation)
class ProfitAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "financial_statement",
        "net_profit_display",
        "reserves_display",
        "reinvestment_display",
        "distributable_profit_display",
        "total_allocated_display",
        "approved_at",
    )

    search_fields = (
        "financial_statement__project__reference",
        "financial_statement__project__title",
        "resolution_reference",
    )

    autocomplete_fields = (
        "financial_statement",
        "approved_by",
    )

    readonly_fields = (
        "net_profit_display",
        "total_allocated_display",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Résultat net")
    def net_profit_display(self, obj):
        return format_money(
            obj.financial_statement.net_profit
        )

    @admin.display(description="Réserves")
    def reserves_display(self, obj):
        total = (
            obj.legal_reserve
            + obj.operating_reserve
            + obj.maintenance_fund
            + obj.risk_fund
        )

        return format_money(total)

    @admin.display(description="Réinvestissement")
    def reinvestment_display(self, obj):
        return format_money(obj.reinvestment_amount)

    @admin.display(description="Bénéfice distribuable")
    def distributable_profit_display(self, obj):
        return format_money(obj.distributable_profit)

    @admin.display(description="Total affecté")
    def total_allocated_display(self, obj):
        return format_money(obj.total_allocated)


# ==========================================================
# DIVIDENDES
# ==========================================================

class DividendEntitlementInline(admin.TabularInline):
    model = DividendEntitlement
    extra = 0
    show_change_link = True

    fields = (
        "stakeholder",
        "ownership_percentage_snapshot",
        "gross_amount",
        "withholding_amount",
        "net_amount",
    )

    readonly_fields = (
        "net_amount",
    )


@admin.register(DividendDeclaration)
class DividendDeclarationAdmin(admin.ModelAdmin):
    list_display = (
        "project_display",
        "declaration_date",
        "declared_amount_display",
        "entitlements_total_display",
        "status",
        "planned_payment_date",
    )

    list_filter = (
        "status",
        "declaration_date",
        "planned_payment_date",
    )

    search_fields = (
        "profit_allocation__financial_statement__project__reference",
        "profit_allocation__financial_statement__project__title",
        "resolution_reference",
    )

    autocomplete_fields = (
        "profit_allocation",
        "approved_by",
    )

    readonly_fields = (
        "entitlements_total_display",
        "created_at",
        "updated_at",
    )

    inlines = (
        DividendEntitlementInline,
    )

    @admin.display(description="Projet")
    def project_display(self, obj):
        return (
            obj.profit_allocation
            .financial_statement
            .project
        )

    @admin.display(description="Montant déclaré")
    def declared_amount_display(self, obj):
        return format_money(obj.declared_amount)

    @admin.display(description="Droits calculés")
    def entitlements_total_display(self, obj):
        return format_money(obj.total_entitlements)


@admin.register(DividendEntitlement)
class DividendEntitlementAdmin(admin.ModelAdmin):
    list_display = (
        "declaration",
        "stakeholder",
        "ownership_percentage_snapshot",
        "gross_amount_display",
        "withholding_display",
        "net_amount_display",
        "paid_amount_display",
    )

    list_filter = (
        "declaration__status",
        "stakeholder__holder_type",
    )

    search_fields = (
        "stakeholder__legal_name",
        "declaration__profit_allocation__financial_statement__project__reference",
    )

    autocomplete_fields = (
        "declaration",
        "stakeholder",
    )

    readonly_fields = (
        "net_amount",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Montant brut")
    def gross_amount_display(self, obj):
        return format_money(obj.gross_amount)

    @admin.display(description="Retenues")
    def withholding_display(self, obj):
        return format_money(obj.withholding_amount)

    @admin.display(description="Montant net")
    def net_amount_display(self, obj):
        return format_money(obj.net_amount)

    @admin.display(description="Déjà payé")
    def paid_amount_display(self, obj):
        amount = obj.payments.filter(
            status=DividendPayment.Status.PAID,
        ).aggregate(
            total=Sum("amount"),
        )["total"] or 0

        return format_money(amount)


@admin.register(DividendPayment)
class DividendPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "stakeholder_display",
        "amount_display",
        "status",
        "payment_date",
        "payment_method",
        "transaction_reference",
    )

    list_filter = (
        "status",
        "payment_date",
        "payment_method",
    )

    search_fields = (
        "entitlement__stakeholder__legal_name",
        "transaction_reference",
        "entitlement__declaration__profit_allocation__financial_statement__project__reference",
    )

    autocomplete_fields = (
        "entitlement",
        "processed_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Bénéficiaire")
    def stakeholder_display(self, obj):
        return obj.entitlement.stakeholder.legal_name

    @admin.display(description="Montant")
    def amount_display(self, obj):
        return format_money(obj.amount)


# ==========================================================
# RÉINVESTISSEMENT
# ==========================================================

@admin.register(ReinvestmentDecision)
class ReinvestmentDecisionAdmin(admin.ModelAdmin):
    list_display = (
        "source_project",
        "destination_project",
        "amount_display",
        "decision_date",
        "resolution_reference",
        "approved_by",
    )

    list_filter = (
        "decision_date",
        "source_project__postal_office__region",
    )

    search_fields = (
        "source_project__reference",
        "source_project__title",
        "destination_project__reference",
        "destination_project__title",
        "resolution_reference",
    )

    autocomplete_fields = (
        "source_project",
        "destination_project",
        "approved_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Montant")
    def amount_display(self, obj):
        return format_money(obj.amount)


# ==========================================================
# SUIVI OPÉRATIONNEL
# ==========================================================

@admin.register(ProjectMilestone)
class ProjectMilestoneAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "title",
        "planned_end_date",
        "progress_percentage",
        "status",
        "planned_budget_display",
        "actual_cost_display",
        "responsible",
    )

    list_filter = (
        "status",
        "planned_end_date",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "title",
        "description",
    )

    autocomplete_fields = (
        "project",
        "responsible",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Budget prévu")
    def planned_budget_display(self, obj):
        return format_money(obj.planned_budget)

    @admin.display(description="Coût réel")
    def actual_cost_display(self, obj):
        return format_money(obj.actual_cost)


@admin.register(ProjectIncident)
class ProjectIncidentAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "title",
        "severity_badge",
        "status",
        "reported_by",
        "reported_at",
        "resolved_at",
    )

    list_filter = (
        "severity",
        "status",
        "reported_at",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "title",
        "description",
        "corrective_action",
    )

    autocomplete_fields = (
        "project",
        "reported_by",
    )

    readonly_fields = (
        "reported_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Gravité")
    def severity_badge(self, obj):
        colors = {
            obj.Severity.LOW: "#198754",
            obj.Severity.MODERATE: "#0d6efd",
            obj.Severity.HIGH: "#fd7e14",
            obj.Severity.CRITICAL: "#dc3545",
        }

        return format_html(
            '<span style="color:{};font-weight:700;">● {}</span>',
            colors.get(obj.severity, "#6c757d"),
            obj.get_severity_display(),
        )


@admin.register(ProjectMeeting)
class ProjectMeetingAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "title",
        "meeting_date",
        "organized_by",
        "participant_count",
    )

    list_filter = (
        "meeting_date",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "title",
        "agenda",
        "minutes",
        "decisions",
    )

    autocomplete_fields = (
        "project",
        "organized_by",
        "participants",
    )

    filter_horizontal = (
        "participants",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Participants")
    def participant_count(self, obj):
        return obj.participants.count()


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "document_type",
        "title",
        "version",
        "is_validated",
        "uploaded_by",
        "created_at",
    )

    list_filter = (
        "document_type",
        "is_validated",
        "created_at",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "title",
        "version",
    )

    autocomplete_fields = (
        "project",
        "uploaded_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(CommunityImpact)
class CommunityImpactAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "jobs_created",
        "direct_beneficiaries",
        "women_beneficiaries",
        "youth_beneficiaries",
        "annual_income_display",
        "assets_created_display",
        "measurement_date",
    )

    list_filter = (
        "measurement_date",
        "project__sector",
        "project__postal_office__region",
    )

    search_fields = (
        "project__reference",
        "project__title",
        "environmental_benefits",
        "social_benefits",
    )

    autocomplete_fields = (
        "project",
        "verified_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    @admin.display(description="Revenus générés")
    def annual_income_display(self, obj):
        return format_money(obj.annual_income_generated)

    @admin.display(description="Actifs créés")
    def assets_created_display(self, obj):
        return format_money(obj.assets_created_value)


# ==========================================================
# PERSONNALISATION DE L'ADMINISTRATION
# ==========================================================

admin.site.site_header = "Administration YAAYESS"
admin.site.site_title = "YAAYESS"
admin.site.index_title = (
    "Gestion de l'infrastructure financière communautaire"
)