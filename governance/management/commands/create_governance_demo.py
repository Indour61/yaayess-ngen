from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from community_investment.models import (
    CommunityInvestmentProject,
    InvestmentEligibilityPolicy,
    PostalOffice,
    PostalRegion,
)
from epargnecredit.models import Group as SavingsGroup
from governance.models import (
    GovernanceInstance,
    GovernanceTask,
    GovernanceWorkflow,
)


class Command(BaseCommand):
    help = (
        "Crée un projet communautaire de démonstration "
        "et son instance de gouvernance."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()

        user = (
            User.objects
            .filter(is_active=True, is_superuser=True)
            .order_by("id")
            .first()
        )

        if user is None:
            user = (
                User.objects
                .filter(is_active=True)
                .order_by("id")
                .first()
            )

        if user is None:
            raise CommandError(
                "Aucun utilisateur actif n’est disponible. "
                "Créez d’abord un utilisateur ou un superutilisateur."
            )

        # ==================================================
        # 1. RÉGION POSTALE
        # ==================================================

        region, region_created = PostalRegion.objects.get_or_create(
            code="DKR",
            defaults={
                "name": "Direction régionale de Dakar",
                "manager": user,
                "description": (
                    "Région postale créée pour la démonstration "
                    "du moteur de gouvernance YAAYESS."
                ),
                "is_active": True,
            },
        )

        # ==================================================
        # 2. BUREAU DE POSTE
        # ==================================================

        office, office_created = PostalOffice.objects.get_or_create(
            code="DKR-PLATEAU-01",
            defaults={
                "region": region,
                "name": "Bureau de Poste Dakar Plateau",
                "city": "Dakar",
                "address": "Dakar Plateau",
                "manager": user,
                "is_active": True,
            },
        )

        office.authorized_users.add(user)

        # ==================================================
        # 3. GROUPEMENT D’ÉPARGNE-CRÉDIT
        # ==================================================

        savings_group = (
            SavingsGroup.objects
            .filter(nom="Groupement YAAYESS Démonstration")
            .first()
        )

        group_created = False

        if savings_group is None:
            savings_group = SavingsGroup.objects.create(
                nom="Groupement YAAYESS Démonstration",
                admin=user,
                montant_base=Decimal("500000.00"),
                is_active=True,
            )
            group_created = True

        # ==================================================
        # 4. POLITIQUE D’ÉLIGIBILITÉ
        # ==================================================

        policy = (
            InvestmentEligibilityPolicy.objects
            .filter(is_active=True)
            .order_by("-effective_from")
            .first()
        )

        policy_created = False

        if policy is None:
            policy = InvestmentEligibilityPolicy.objects.create(
                name=(
                    "Politique standard d’investissement "
                    "communautaire"
                ),
                minimum_capital=Decimal("30000000.00"),
                minimum_group_age_months=12,
                minimum_active_members=10,
                minimum_savings_regularity_rate=Decimal("80.00"),
                minimum_governance_score=Decimal("70.00"),
                minimum_internal_reserve_rate=Decimal("10.00"),
                minimum_group_equity_rate=Decimal("60.00"),
                suggested_poste_equity_rate=Decimal("12.00"),
                suggested_yaayess_equity_rate=Decimal("8.00"),
                requires_general_assembly_resolution=True,
                requires_business_plan=True,
                requires_feasibility_study=True,
                requires_verified_financial_statements=True,
                requires_environmental_assessment=False,
                requires_conflict_of_interest_declaration=True,
                requires_signed_investment_agreement=True,
                is_active=True,
                created_by=user,
            )
            policy_created = True

        # ==================================================
        # 5. PROJET D’INVESTISSEMENT
        # ==================================================

        project = (
            CommunityInvestmentProject.objects
            .filter(
                title="Projet maraîcher communautaire pilote",
                group=savings_group,
            )
            .first()
        )

        project_created = False

        if project is None:
            project = CommunityInvestmentProject.objects.create(
                group=savings_group,
                postal_office=office,
                eligibility_policy=policy,
                title="Projet maraîcher communautaire pilote",
                description=(
                    "Projet pilote de production maraîchère, "
                    "de transformation et de commercialisation, "
                    "porté par un groupement d’épargne-crédit."
                ),
                sector=(
                    CommunityInvestmentProject.Sector.AGRICULTURE
                ),
                project_location="Région de Dakar",
                project_lead=user,

                # Le groupement dépasse le seuil de 30 millions.
                capital_at_submission=Decimal("35000000.00"),

                # Coût global du projet.
                total_project_cost=Decimal("40000000.00"),

                # Participation prévue du groupement.
                group_planned_equity=Decimal("32000000.00"),

                expected_return_rate=Decimal("18.00"),
                expected_jobs=25,
                expected_beneficiaries=120,

                governance_score=Decimal("90.00"),
                savings_regularity_rate=Decimal("92.00"),

                status=(
                    CommunityInvestmentProject.Status.ELIGIBLE
                ),
                eligibility_status=(
                    CommunityInvestmentProject
                    .EligibilityStatus
                    .ELIGIBLE
                ),
                risk_level=(
                    CommunityInvestmentProject.RiskLevel.LOW
                ),
                progress_percentage=Decimal("0.00"),

                general_assembly_resolution_reference=(
                    "PV-AG-YAAYESS-DEMO-001"
                ),
                general_assembly_resolution_date=(
                    timezone.localdate()
                ),

                planned_start_date=timezone.localdate(),
                created_by=user,
            )

            project_created = True

        # ==================================================
        # 6. WORKFLOW STANDARD
        # ==================================================

        workflow = (
            GovernanceWorkflow.objects
            .filter(
                code="COMMUNITY_INVESTMENT",
                version=1,
                status=GovernanceWorkflow.Status.ACTIVE,
            )
            .first()
        )

        if workflow is None:
            raise CommandError(
                "Le workflow COMMUNITY_INVESTMENT v1 est absent. "
                "Exécutez d’abord : "
                "python manage.py setup_investment_workflow"
            )

        first_stage = workflow.first_stage

        if first_stage is None:
            raise CommandError(
                "Le workflow ne possède aucune étape initiale active."
            )

        # ==================================================
        # 7. INSTANCE DE GOUVERNANCE
        # ==================================================

        now = timezone.now()

        instance, instance_created = (
            GovernanceInstance.objects.get_or_create(
                project=project,
                defaults={
                    "workflow": workflow,
                    "current_stage": first_stage,
                    "status": GovernanceInstance.Status.ACTIVE,
                    "governance_score": Decimal("0.00"),
                    "started_by": user,
                    "started_at": now,
                    "stage_started_at": now,
                    "due_at": (
                        now
                        + timezone.timedelta(
                            days=first_stage.target_duration_days,
                        )
                    ),
                    "last_action_by": user,
                    "last_action_at": now,
                },
            )
        )

        # ==================================================
        # 8. PREMIÈRE TÂCHE
        # ==================================================

        task, task_created = GovernanceTask.objects.get_or_create(
            instance=instance,
            stage=first_stage,
            title="Exécuter la pré-éligibilité automatique",
            defaults={
                "description": (
                    "Vérifier automatiquement le capital, "
                    "la gouvernance, la régularité de l’épargne, "
                    "les documents, les tâches et le niveau de risque."
                ),
                "task_type": GovernanceTask.TaskType.ANALYSIS,
                "priority": GovernanceTask.Priority.HIGH,
                "status": GovernanceTask.Status.PENDING,
                "assigned_group": first_stage.responsible_group,
                "assigned_by": user,
                "assigned_at": (
                    now
                    if first_stage.responsible_group
                    else None
                ),
                "due_at": (
                    now
                    + timezone.timedelta(
                        days=first_stage.target_duration_days,
                    )
                ),
                "is_mandatory": False,
            },
        )

        # ==================================================
        # RÉSULTAT
        # ==================================================

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Démonstration de gouvernance créée avec succès."
            )
        )

        self.stdout.write(
            f"Utilisateur : {user}"
        )
        self.stdout.write(
            f"Région : {region} — créée : {region_created}"
        )
        self.stdout.write(
            f"Bureau : {office} — créé : {office_created}"
        )
        self.stdout.write(
            f"Groupement : {savings_group} — créé : {group_created}"
        )
        self.stdout.write(
            f"Politique : {policy} — créée : {policy_created}"
        )
        self.stdout.write(
            f"Projet : {project.reference} — créé : {project_created}"
        )
        self.stdout.write(
            f"Instance : {instance.reference} — créée : "
            f"{instance_created}"
        )
        self.stdout.write(
            f"Étape actuelle : {instance.current_stage}"
        )
        self.stdout.write(
            f"Tâche : {task.reference} — créée : {task_created}"
        )