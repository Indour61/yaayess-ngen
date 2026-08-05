from django.apps import AppConfig


class GovernanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "governance"
    verbose_name = "Gouvernance des investissements"

    def ready(self) -> None:
        import governance.signals  # noqa: F401

