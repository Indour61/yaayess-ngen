from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from governance.models import (
    GovernanceStage,
    GovernanceTransition,
    GovernanceWorkflow,
)


class Command(BaseCommand):
    help = (
        "Crée ou met à jour le workflow standard "
        "de gouvernance des investissements communautaires."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        groups = {
            "AUTOMATION": Group.objects.get_or_create(
                name="Moteur automatique"
            )[0],
            "POSTAL_OFFICE": Group.objects.get_or_create(
                name="Bureaux de poste"
            )[0],
            "REGIONAL": Group.objects.get_or_create(
                name="Directions régionales"
            )[0],
            "CENTRAL": Group.objects.get_or_create(
                name="Direction des investissements communautaires"
            )[0],
            "COMMITTEE": Group.objects.get_or_create(
                name="Comité d’investissement"
            )[0],
            "LEGAL": Group.objects.get_or_create(
                name="Cellule juridique"
            )[0],
            "AUDIT": Group.objects.get_or_create(
                name="Audit et contrôle"
            )[0],
            "FINANCE": Group.objects.get_or_create(
                name="Gestion financière des projets"
            )[0],
        }

        workflow, workflow_created = (
            GovernanceWorkflow.objects.update_or_create(
                code="COMMUNITY_INVESTMENT",
                version=1,
                defaults={
                    "name": (
                        "Gouvernance standard des investissements "
                        "communautaires"
                    ),
                    "description": (
                        "Workflow complet d’instruction, de validation, "
                        "d’exécution et de suivi des investissements "
                        "communautaires."
                    ),
                    "status": GovernanceWorkflow.Status.DRAFT,
                    "is_default": False,
                    "allow_parallel_tasks": True,
                },
            )
        )

        stages_data = [
            {
                "code": "PRE_ELIGIBILITY",
                "name": "Pré-éligibilité automatique",
                "order": 10,
                "stage_type": GovernanceStage.StageType.AUTOMATED,
                "group": groups["AUTOMATION"],
                "duration": 1,
                "is_initial": True,
            },
            {
                "code": "POSTAL_OFFICE_REVIEW",
                "name": "Instruction par le bureau de poste",
                "order": 20,
                "stage_type": GovernanceStage.StageType.REVIEW,
                "group": groups["POSTAL_OFFICE"],
                "duration": 5,
            },
            {
                "code": "REGIONAL_REVIEW",
                "name": "Instruction régionale",
                "order": 30,
                "stage_type": GovernanceStage.StageType.REVIEW,
                "group": groups["REGIONAL"],
                "duration": 5,
            },
            {
                "code": "CENTRAL_REVIEW",
                "name": (
                    "Direction des investissements communautaires"
                ),
                "order": 40,
                "stage_type": GovernanceStage.StageType.REVIEW,
                "group": groups["CENTRAL"],
                "duration": 7,
            },
            {
                "code": "INVESTMENT_COMMITTEE",
                "name": "Comité d’investissement",
                "order": 50,
                "stage_type": GovernanceStage.StageType.COMMITTEE,
                "group": groups["COMMITTEE"],
                "duration": 7,
            },
            {
                "code": "LEGAL_STRUCTURING",
                "name": "Structuration juridique",
                "order": 60,
                "stage_type": GovernanceStage.StageType.LEGAL,
                "group": groups["LEGAL"],
                "duration": 10,
            },
            {
                "code": "CAPITALIZATION",
                "name": "Validation du capital",
                "order": 70,
                "stage_type": GovernanceStage.StageType.FINANCIAL,
                "group": groups["FINANCE"],
                "duration": 10,
            },
            {
                "code": "PROJECT_EXECUTION",
                "name": "Exécution et exploitation du projet",
                "order": 80,
                "stage_type": GovernanceStage.StageType.EXECUTION,
                "group": groups["CENTRAL"],
                "duration": 30,
            },
            {
                "code": "AUDIT",
                "name": "Audit et contrôle",
                "order": 90,
                "stage_type": GovernanceStage.StageType.AUDIT,
                "group": groups["AUDIT"],
                "duration": 10,
            },
            {
                "code": "PROFIT_ALLOCATION",
                "name": "Affectation du résultat",
                "order": 100,
                "stage_type": GovernanceStage.StageType.FINANCIAL,
                "group": groups["FINANCE"],
                "duration": 5,
            },
            {
                "code": "REINVESTMENT",
                "name": "Distribution ou réinvestissement",
                "order": 110,
                "stage_type": GovernanceStage.StageType.CLOSURE,
                "group": groups["COMMITTEE"],
                "duration": 5,
                "is_final": True,
            },
        ]

        stages = {}

        for data in stages_data:
            stage, _ = GovernanceStage.objects.update_or_create(
                workflow=workflow,
                code=data["code"],
                defaults={
                    "name": data["name"],
                    "order": data["order"],
                    "stage_type": data["stage_type"],
                    "responsible_group": data["group"],
                    "target_duration_days": data["duration"],
                    "escalation_after_days": data["duration"] + 2,
                    "is_initial": data.get("is_initial", False),
                    "is_final": data.get("is_final", False),
                    "is_active": True,
                    "is_mandatory": True,
                    "requires_decision": (
                        data["stage_type"]
                        != GovernanceStage.StageType.AUTOMATED
                    ),
                    "requires_comment": True,
                    "requires_document": (
                        data["code"]
                        in {
                            "POSTAL_OFFICE_REVIEW",
                            "CENTRAL_REVIEW",
                            "LEGAL_STRUCTURING",
                            "AUDIT",
                        }
                    ),
                },
            )

            stages[data["code"]] = stage

        ordered_codes = [item["code"] for item in stages_data]

        for index in range(len(ordered_codes) - 1):
            from_code = ordered_codes[index]
            to_code = ordered_codes[index + 1]

            trigger = (
                GovernanceTransition.Trigger.AUTOMATIC
                if from_code == "PRE_ELIGIBILITY"
                else GovernanceTransition.Trigger.APPROVE
            )

            GovernanceTransition.objects.update_or_create(
                workflow=workflow,
                code=f"{from_code}_TO_{to_code}",
                defaults={
                    "name": (
                        f"{stages[from_code].name} vers "
                        f"{stages[to_code].name}"
                    ),
                    "from_stage": stages[from_code],
                    "to_stage": stages[to_code],
                    "trigger": trigger,
                    "is_active": True,
                    "requires_comment": (
                        trigger
                        != GovernanceTransition.Trigger.AUTOMATIC
                    ),
                    "requires_document": False,
                    "minimum_score": 80,
                },
            )

        workflow.status = GovernanceWorkflow.Status.ACTIVE
        workflow.is_default = True
        workflow.save()

        self.stdout.write(
            self.style.SUCCESS(
                "Workflow standard créé avec succès."
            )
        )
        self.stdout.write(
            f"Workflow nouvellement créé : {workflow_created}"
        )
        self.stdout.write(
            f"Étapes : {workflow.stages.count()}"
        )
        self.stdout.write(
            f"Transitions : {workflow.transitions.count()}"
        )