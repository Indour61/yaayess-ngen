from django.contrib import admin

from .models import WeeklyExecutiveDashboard


@admin.register(WeeklyExecutiveDashboard)
class WeeklyExecutiveDashboardAdmin(admin.ModelAdmin):
    list_display = (
        "week_number",
        "period_start",
        "period_end",
        "overall_status",
        "progress_percentage",
        "is_published",
        "updated_at",
    )

    list_filter = (
        "overall_status",
        "is_published",
        "period_start",
    )

    search_fields = (
        "highlights",
        "achievements",
        "difficulties",
        "major_risks",
        "expected_decisions",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Période",
            {
                "fields": (
                    "week_number",
                    "period_start",
                    "period_end",
                    "is_published",
                )
            },
        ),
        (
            "État général",
            {
                "fields": (
                    "overall_status",
                    "progress_percentage",
                    "planning_status",
                    "budget_status",
                    "quality_status",
                    "platform_status",
                    "user_satisfaction_status",
                )
            },
        ),
        (
            "Adoption",
            {
                "fields": (
                    "accounts_created",
                    "active_users",
                    "groups_created",
                    "registered_members",
                )
            },
        ),
        (
            "Finance communautaire",
            {
                "fields": (
                    "contributions_count",
                    "contributions_amount",
                    "savings_deposits_count",
                    "savings_amount",
                    "credits_granted_count",
                    "credits_amount",
                    "repayments_count",
                    "investments_count",
                    "investments_amount",
                )
            },
        ),
        (
            "Performance technique",
            {
                "fields": (
                    "platform_availability",
                    "successful_transaction_rate",
                    "average_response_time",
                    "critical_incidents",
                )
            },
        ),
        (
            "Synthèse exécutive",
            {
                "fields": (
                    "highlights",
                    "achievements",
                    "difficulties",
                    "opportunities",
                    "major_risks",
                    "expected_decisions",
                    "next_week_priorities",
                    "project_manager_comment",
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
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user

        super().save_model(request, obj, form, change)