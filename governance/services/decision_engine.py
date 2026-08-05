from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from community_investment.models import (
    CommunityInvestmentProject,
    ProjectDocument,
)
from governance.models import (
    GovernanceDecisionLog,
    GovernanceInstance,
    GovernanceStage,
    GovernanceTask,
    GovernanceTransition,
)

ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


# ==========================================================
# TYPES DE DÉCISION
# ==========================================================

class DecisionCode:
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_INFO = "REQUEST_INFO"
    ADVANCE = "ADVANCE"
    BLOCK = "BLOCK"
    MANUAL_REVIEW = "MANUAL_REVIEW"


# ==========================================================
# RÉSULTAT DU MOTEUR
# ==========================================================

@dataclass
class DecisionCriterionResult:
    code: str
    label: str
    passed: bool
    score: Decimal
    weight: Decimal
    message: str
    blocking: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def weighted_score(self) -> Decimal:
        return (
            self.score
            * self.weight
            / HUNDRED
        ).quantize(Decimal("0.01"))


@dataclass
class GovernanceDecisionResult:
    decision: str
    global_score: Decimal
    eligible: bool
    can_advance: bool
    recommended_transition_code: str | None
    summary: str
    criteria: list[DecisionCriterionResult]
    blocking_reasons: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)

        data["global_score"] = str(self.global_score)

        for criterion in data["criteria"]:
            criterion["score"] = str(criterion["score"])
            criterion["weight"] = str(criterion["weight"])
            criterion["weighted_score"] = str(
                next(
                    item.weighted_score
                    for item in self.criteria
                    if item.code == criterion["code"]
                )
            )

        return data


# ==========================================================
# CONFIGURATION DU SCORING
# ==========================================================

DEFAULT_WEIGHTS = {
    "CAPITAL": Decimal("25.00"),
    "GOVERNANCE": Decimal("20.00"),
    "SAVINGS_REGULARITY": Decimal("15.00"),
    "DOCUMENTS": Decimal("15.00"),
    "TASKS": Decimal("10.00"),
    "RISK": Decimal("15.00"),
}

APPROVAL_SCORE = Decimal("80.00")
MANUAL_REVIEW_SCORE = Decimal("60.00")


# ==========================================================
# MOTEUR PRINCIPAL
# ==========================================================

class GovernanceDecisionEngine:
    """
    Moteur d'aide à la décision du module Governance.

    Il évalue un dossier à partir :
    - du projet d'investissement ;
    - de sa politique d'éligibilité ;
    - de l'étape actuelle ;
    - des documents ;
    - des tâches ;
    - du niveau de risque ;
    - des transitions configurées.
    """

    def __init__(
        self,
        *,
        instance: GovernanceInstance,
        actor=None,
        weights: dict[str, Decimal] | None = None,
    ):
        self.instance = instance
        self.project = instance.project
        self.workflow = instance.workflow
        self.stage = instance.current_stage
        self.actor = actor
        self.weights = weights or DEFAULT_WEIGHTS

    def evaluate(self) -> GovernanceDecisionResult:
        if self.stage is None:
            raise ValidationError(
                "L’instance ne possède aucune étape actuelle."
            )

        criteria = [
            self._evaluate_capital(),
            self._evaluate_governance(),
            self._evaluate_savings_regularity(),
            self._evaluate_documents(),
            self._evaluate_tasks(),
            self._evaluate_risk(),
        ]

        blocking_reasons = [
            criterion.message
            for criterion in criteria
            if criterion.blocking and not criterion.passed
        ]

        warnings = [
            criterion.message
            for criterion in criteria
            if not criterion.blocking and not criterion.passed
        ]

        global_score = sum(
            (
                criterion.weighted_score
                for criterion in criteria
            ),
            ZERO,
        ).quantize(Decimal("0.01"))

        eligible = not blocking_reasons

        recommended_transition = (
            self._find_recommended_transition(
                global_score=global_score,
                eligible=eligible,
            )
        )

        can_advance = (
            eligible
            and recommended_transition is not None
        )

        decision = self._resolve_decision(
            global_score=global_score,
            eligible=eligible,
            transition=recommended_transition,
        )

        summary = self._build_summary(
            decision=decision,
            global_score=global_score,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
        )

        return GovernanceDecisionResult(
            decision=decision,
            global_score=global_score,
            eligible=eligible,
            can_advance=can_advance,
            recommended_transition_code=(
                recommended_transition.code
                if recommended_transition
                else None
            ),
            summary=summary,
            criteria=criteria,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
        )

    # ======================================================
    # CRITÈRE CAPITAL
    # ======================================================

    def _evaluate_capital(
        self,
    ) -> DecisionCriterionResult:
        policy = self.project.eligibility_policy
        minimum = policy.minimum_capital
        current = self.project.capital_at_submission

        if minimum <= ZERO:
            score = HUNDRED
        else:
            score = min(
                current / minimum * HUNDRED,
                HUNDRED,
            )

        passed = current >= minimum

        return DecisionCriterionResult(
            code="CAPITAL",
            label="Capitalisation du groupement",
            passed=passed,
            score=score,
            weight=self.weights["CAPITAL"],
            blocking=True,
            message=(
                "Le capital minimum requis est atteint."
                if passed
                else (
                    "Le capital du groupement est insuffisant : "
                    f"{current:,.0f} FCFA sur "
                    f"{minimum:,.0f} FCFA requis."
                )
            ),
            details={
                "capital": str(current),
                "minimum_capital": str(minimum),
            },
        )

    # ======================================================
    # CRITÈRE GOUVERNANCE
    # ======================================================

    def _evaluate_governance(
        self,
    ) -> DecisionCriterionResult:
        policy = self.project.eligibility_policy
        minimum = policy.minimum_governance_score
        current = self.project.governance_score

        passed = current >= minimum

        return DecisionCriterionResult(
            code="GOVERNANCE",
            label="Qualité de la gouvernance",
            passed=passed,
            score=min(current, HUNDRED),
            weight=self.weights["GOVERNANCE"],
            blocking=True,
            message=(
                "Le niveau de gouvernance est conforme."
                if passed
                else (
                    "Le score de gouvernance est insuffisant : "
                    f"{current}% sur {minimum}% requis."
                )
            ),
            details={
                "score": str(current),
                "minimum_score": str(minimum),
            },
        )

    # ======================================================
    # CRITÈRE RÉGULARITÉ DE L’ÉPARGNE
    # ======================================================

    def _evaluate_savings_regularity(
        self,
    ) -> DecisionCriterionResult:
        policy = self.project.eligibility_policy
        minimum = policy.minimum_savings_regularity_rate
        current = self.project.savings_regularity_rate

        passed = current >= minimum

        return DecisionCriterionResult(
            code="SAVINGS_REGULARITY",
            label="Régularité de l’épargne",
            passed=passed,
            score=min(current, HUNDRED),
            weight=self.weights["SAVINGS_REGULARITY"],
            blocking=True,
            message=(
                "La régularité de l’épargne est conforme."
                if passed
                else (
                    "La régularité de l’épargne est insuffisante : "
                    f"{current}% sur {minimum}% requis."
                )
            ),
            details={
                "regularity_rate": str(current),
                "minimum_rate": str(minimum),
            },
        )

    # ======================================================
    # CRITÈRE DOCUMENTAIRE
    # ======================================================

    def _evaluate_documents(
        self,
    ) -> DecisionCriterionResult:
        required_types = self._get_required_document_types()

        if not required_types:
            return DecisionCriterionResult(
                code="DOCUMENTS",
                label="Complétude documentaire",
                passed=True,
                score=HUNDRED,
                weight=self.weights["DOCUMENTS"],
                message="Aucun document obligatoire n’est configuré.",
            )

        validated_documents = set(
            self.project.documents.filter(
                document_type__in=required_types,
                is_validated=True,
            ).values_list(
                "document_type",
                flat=True,
            )
        )

        missing = [
            document_type
            for document_type in required_types
            if document_type not in validated_documents
        ]

        validated_count = (
            len(required_types) - len(missing)
        )

        score = (
            Decimal(validated_count)
            / Decimal(len(required_types))
            * HUNDRED
        ).quantize(Decimal("0.01"))

        passed = not missing

        return DecisionCriterionResult(
            code="DOCUMENTS",
            label="Complétude documentaire",
            passed=passed,
            score=score,
            weight=self.weights["DOCUMENTS"],
            blocking=self.stage.requires_document,
            message=(
                "Tous les documents obligatoires sont validés."
                if passed
                else (
                    "Documents obligatoires manquants ou non validés : "
                    + ", ".join(missing)
                )
            ),
            details={
                "required": required_types,
                "validated": list(validated_documents),
                "missing": missing,
            },
        )

    def _get_required_document_types(
        self,
    ) -> list[str]:
        policy = self.project.eligibility_policy
        required = []

        if policy.requires_business_plan:
            required.append(
                ProjectDocument.DocumentType.BUSINESS_PLAN
            )

        if policy.requires_feasibility_study:
            required.append(
                ProjectDocument.DocumentType.FEASIBILITY_STUDY
            )

        if policy.requires_general_assembly_resolution:
            required.append(
                ProjectDocument.DocumentType.RESOLUTION
            )

        if policy.requires_signed_investment_agreement:
            required.append(
                ProjectDocument.DocumentType.INVESTMENT_AGREEMENT
            )

        return required

    # ======================================================
    # CRITÈRE DES TÂCHES
    # ======================================================

    def _evaluate_tasks(
        self,
    ) -> DecisionCriterionResult:
        tasks = self.instance.tasks.filter(
            stage=self.stage,
            is_mandatory=True,
        )

        total = tasks.count()

        if total == 0:
            return DecisionCriterionResult(
                code="TASKS",
                label="Tâches obligatoires",
                passed=True,
                score=HUNDRED,
                weight=self.weights["TASKS"],
                message=(
                    "Aucune tâche obligatoire n’est configurée "
                    "pour cette étape."
                ),
            )

        completed = tasks.filter(
            status=GovernanceTask.Status.COMPLETED,
        ).count()

        score = (
            Decimal(completed)
            / Decimal(total)
            * HUNDRED
        ).quantize(Decimal("0.01"))

        pending = total - completed
        passed = pending == 0

        return DecisionCriterionResult(
            code="TASKS",
            label="Exécution des tâches obligatoires",
            passed=passed,
            score=score,
            weight=self.weights["TASKS"],
            blocking=True,
            message=(
                "Toutes les tâches obligatoires sont terminées."
                if passed
                else (
                    f"{pending} tâche(s) obligatoire(s) "
                    "restent à terminer."
                )
            ),
            details={
                "total": total,
                "completed": completed,
                "pending": pending,
            },
        )

    # ======================================================
    # CRITÈRE RISQUE
    # ======================================================

    def _evaluate_risk(
        self,
    ) -> DecisionCriterionResult:
        risk_scores = {
            CommunityInvestmentProject.RiskLevel.LOW:
                Decimal("100.00"),
            CommunityInvestmentProject.RiskLevel.MODERATE:
                Decimal("75.00"),
            CommunityInvestmentProject.RiskLevel.HIGH:
                Decimal("45.00"),
            CommunityInvestmentProject.RiskLevel.CRITICAL:
                Decimal("10.00"),
        }

        score = risk_scores.get(
            self.project.risk_level,
            Decimal("50.00"),
        )

        passed = (
            self.project.risk_level
            != CommunityInvestmentProject.RiskLevel.CRITICAL
        )

        return DecisionCriterionResult(
            code="RISK",
            label="Niveau de risque",
            passed=passed,
            score=score,
            weight=self.weights["RISK"],
            blocking=not passed,
            message=(
                "Le niveau de risque permet la poursuite du dossier."
                if passed
                else (
                    "Le projet présente un risque critique et doit "
                    "être soumis à une revue renforcée."
                )
            ),
            details={
                "risk_level": self.project.risk_level,
                "risk_label": self.project.get_risk_level_display(),
            },
        )

    # ======================================================
    # TRANSITION RECOMMANDÉE
    # ======================================================

    def _find_recommended_transition(
        self,
        *,
        global_score: Decimal,
        eligible: bool,
    ) -> GovernanceTransition | None:
        transitions = (
            GovernanceTransition.objects
            .filter(
                workflow=self.workflow,
                from_stage=self.stage,
                is_active=True,
            )
            .select_related(
                "to_stage",
            )
            .order_by(
                "to_stage__order",
            )
        )

        if not eligible:
            preferred_triggers = [
                GovernanceTransition.Trigger.REQUEST_INFO,
                GovernanceTransition.Trigger.RETURN,
                GovernanceTransition.Trigger.REJECT,
            ]
        else:
            preferred_triggers = [
                GovernanceTransition.Trigger.APPROVE,
                GovernanceTransition.Trigger.SUBMIT,
                GovernanceTransition.Trigger.AUTOMATIC,
                GovernanceTransition.Trigger.COMPLETE,
            ]

        for trigger in preferred_triggers:
            for transition in transitions.filter(
                trigger=trigger,
            ):
                if (
                    transition.minimum_score is not None
                    and global_score < transition.minimum_score
                ):
                    continue

                return transition

        return None

    # ======================================================
    # DÉCISION FINALE
    # ======================================================

    def _resolve_decision(
        self,
        *,
        global_score: Decimal,
        eligible: bool,
        transition: GovernanceTransition | None,
    ) -> str:
        if not eligible:
            if transition and transition.trigger == (
                GovernanceTransition.Trigger.REJECT
            ):
                return DecisionCode.REJECT

            return DecisionCode.REQUEST_INFO

        if global_score >= APPROVAL_SCORE:
            if transition:
                return DecisionCode.ADVANCE

            return DecisionCode.APPROVE

        if global_score >= MANUAL_REVIEW_SCORE:
            return DecisionCode.MANUAL_REVIEW

        return DecisionCode.BLOCK

    def _build_summary(
        self,
        *,
        decision: str,
        global_score: Decimal,
        blocking_reasons: list[str],
        warnings: list[str],
    ) -> str:
        messages = {
            DecisionCode.ADVANCE: (
                "Le dossier satisfait les critères et peut être "
                "transmis à l’étape suivante."
            ),
            DecisionCode.APPROVE: (
                "Le dossier satisfait les critères d’approbation."
            ),
            DecisionCode.REJECT: (
                "Le dossier ne satisfait pas les critères obligatoires."
            ),
            DecisionCode.REQUEST_INFO: (
                "Le dossier nécessite des informations ou corrections "
                "complémentaires."
            ),
            DecisionCode.MANUAL_REVIEW: (
                "Le dossier nécessite une analyse humaine approfondie."
            ),
            DecisionCode.BLOCK: (
                "Le dossier est temporairement bloqué."
            ),
        }

        summary = (
            f"{messages[decision]} "
            f"Score global : {global_score}%."
        )

        if blocking_reasons:
            summary += (
                " Blocages : "
                + " | ".join(blocking_reasons)
            )

        if warnings:
            summary += (
                " Avertissements : "
                + " | ".join(warnings)
            )

        return summary

# ==========================================================
# JOURNALISATION D’UNE DÉCISION
# ==========================================================

def create_decision_log(
    *,
    instance: GovernanceInstance,
    result: GovernanceDecisionResult,
    actor=None,
    from_stage: GovernanceStage | None = None,
    to_stage: GovernanceStage | None = None,
    transition: GovernanceTransition | None = None,
    application_status: str = (
        GovernanceDecisionLog.ApplicationStatus.RECOMMENDED
    ),
    failure_message: str = "",
    actor_ip_address: str | None = None,
    actor_user_agent: str = "",
) -> GovernanceDecisionLog:
    """
    Enregistre un instantané complet et traçable du résultat
    produit par le moteur de décision.

    Les étapes sont transmises explicitement afin de conserver
    l'étape de départ, même après la modification de l'instance.
    """

    evaluated_at = timezone.now()

    criteria_snapshot = [
        {
            "code": criterion.code,
            "label": criterion.label,
            "passed": criterion.passed,
            "score": str(criterion.score),
            "weight": str(criterion.weight),
            "weighted_score": str(criterion.weighted_score),
            "message": criterion.message,
            "blocking": criterion.blocking,
            "details": criterion.details,
        }
        for criterion in result.criteria
    ]

    return GovernanceDecisionLog.objects.create(
        instance=instance,
        project=instance.project,
        workflow=instance.workflow,
        from_stage=from_stage,
        to_stage=to_stage,
        transition=transition,
        decision_code=result.decision,
        application_status=application_status,
        global_score=result.global_score,
        eligible=result.eligible,
        can_advance=result.can_advance,
        summary=result.summary,
        criteria_snapshot=criteria_snapshot,
        blocking_reasons=list(result.blocking_reasons),
        warnings=list(result.warnings),
        engine_snapshot=result.to_dict(),
        actor=actor,
        evaluated_at=evaluated_at,
        applied_at=(
            evaluated_at
            if application_status
            == GovernanceDecisionLog.ApplicationStatus.APPLIED
            else None
        ),
        failure_message=failure_message,
        actor_ip_address=actor_ip_address,
        actor_user_agent=actor_user_agent,
    )


# ==========================================================
# APPLICATION D’UNE DÉCISION
# ==========================================================

@transaction.atomic
def apply_engine_decision(
    *,
    instance: GovernanceInstance,
    actor,
    force: bool = False,
    actor_ip_address: str | None = None,
    actor_user_agent: str = "",
) -> GovernanceDecisionResult:
    """
    Évalue le dossier, journalise le résultat du moteur,
    puis applique éventuellement la transition recommandée.

    Un seul journal est créé pour chaque exécution normale :

    - APPLIED :
      une transition a été appliquée ;

    - NOT_APPLIED :
      le dossier est bloqué, rejeté ou nécessite des compléments ;

    - RECOMMENDED :
      le moteur formule une recommandation sans appliquer
      de transition.
    """

    if instance is None:
        raise ValidationError(
            "Aucune instance de gouvernance n’a été fournie."
        )

    if instance.pk is None:
        raise ValidationError(
            "L’instance de gouvernance doit être enregistrée "
            "avant l’exécution du moteur."
        )

    # Verrouille uniquement la ligne GovernanceInstance.
    # Ne pas ajouter select_related() ici : current_stage et
    # previous_stage sont nullable et PostgreSQL refuserait
    # FOR UPDATE sur le côté nullable d'une jointure externe.
    instance = (
        GovernanceInstance.objects
        .select_for_update()
        .get(pk=instance.pk)
    )

    engine = GovernanceDecisionEngine(
        instance=instance,
        actor=actor,
    )
    result = engine.evaluate()

    from_stage = instance.current_stage
    transition = None
    to_stage = None

    if result.recommended_transition_code:
        transition = (
            GovernanceTransition.objects
            .select_related(
                "from_stage",
                "to_stage",
            )
            .filter(
                workflow=instance.workflow,
                code=result.recommended_transition_code,
                is_active=True,
            )
            .first()
        )

        if transition is not None:
            to_stage = transition.to_stage

    now = timezone.now()

    instance.governance_score = result.global_score
    instance.last_action_by = actor
    instance.last_action_at = now

    # ======================================================
    # DOSSIER BLOQUÉ, REJETÉ OU À COMPLÉTER
    # ======================================================

    if (
        result.decision
        in {
            DecisionCode.BLOCK,
            DecisionCode.REJECT,
            DecisionCode.REQUEST_INFO,
        }
        and not force
    ):
        if result.decision == DecisionCode.REJECT:
            instance.status = GovernanceInstance.Status.REJECTED
            instance.rejection_reason = result.summary
        else:
            instance.status = GovernanceInstance.Status.WAITING
            instance.rejection_reason = ""

        instance.save(
            update_fields=[
                "status",
                "rejection_reason",
                "governance_score",
                "last_action_by",
                "last_action_at",
                "updated_at",
            ]
        )

        create_decision_log(
            instance=instance,
            result=result,
            actor=actor,
            from_stage=from_stage,
            to_stage=to_stage,
            transition=transition,
            application_status=(
                GovernanceDecisionLog
                .ApplicationStatus
                .NOT_APPLIED
            ),
            actor_ip_address=actor_ip_address,
            actor_user_agent=actor_user_agent,
        )

        return result

    # ======================================================
    # REVUE HUMAINE REQUISE
    # ======================================================

    if (
        result.decision == DecisionCode.MANUAL_REVIEW
        and not force
    ):
        instance.status = GovernanceInstance.Status.WAITING
        instance.rejection_reason = ""

        instance.save(
            update_fields=[
                "status",
                "rejection_reason",
                "governance_score",
                "last_action_by",
                "last_action_at",
                "updated_at",
            ]
        )

        create_decision_log(
            instance=instance,
            result=result,
            actor=actor,
            from_stage=from_stage,
            to_stage=to_stage,
            transition=transition,
            application_status=(
                GovernanceDecisionLog
                .ApplicationStatus
                .RECOMMENDED
            ),
            actor_ip_address=actor_ip_address,
            actor_user_agent=actor_user_agent,
        )

        return result

    # ======================================================
    # AUCUNE TRANSITION DISPONIBLE
    # ======================================================

    if transition is None:
        instance.save(
            update_fields=[
                "governance_score",
                "last_action_by",
                "last_action_at",
                "updated_at",
            ]
        )

        create_decision_log(
            instance=instance,
            result=result,
            actor=actor,
            from_stage=from_stage,
            to_stage=None,
            transition=None,
            application_status=(
                GovernanceDecisionLog
                .ApplicationStatus
                .RECOMMENDED
            ),
            actor_ip_address=actor_ip_address,
            actor_user_agent=actor_user_agent,
        )

        return result

    # ======================================================
    # VALIDATION DE LA TRANSITION
    # ======================================================

    if transition.from_stage_id != instance.current_stage_id:
        raise ValidationError(
            "La transition recommandée ne correspond plus "
            "à l’étape actuelle du dossier."
        )

    if transition.workflow_id != instance.workflow_id:
        raise ValidationError(
            "La transition recommandée n’appartient pas "
            "au workflow de l’instance."
        )

    _check_transition_permission(
        transition=transition,
        actor=actor,
    )

    next_stage = transition.to_stage

    # ======================================================
    # CLÔTURE DES TÂCHES DE L’ÉTAPE QUITTÉE
    # ======================================================

    if from_stage is not None:
        instance.tasks.filter(
            stage=from_stage,
        ).exclude(
            status__in=[
                GovernanceTask.Status.COMPLETED,
                GovernanceTask.Status.CANCELLED,
            ],
        ).update(
            status=GovernanceTask.Status.COMPLETED,
            completed_at=now,
            completed_by=actor,
            completion_comment=(
                "Tâche clôturée automatiquement après validation "
                "de l’étape et application de la transition."
            ),
        )

    # ======================================================
    # MISE À JOUR DE L’INSTANCE
    # ======================================================

    instance.previous_stage = from_stage
    instance.current_stage = next_stage
    instance.stage_started_at = now
    instance.last_action_by = actor
    instance.last_action_at = now
    instance.suspended_at = None
    instance.suspension_reason = ""
    instance.rejection_reason = ""

    if next_stage.is_final:
        instance.status = GovernanceInstance.Status.COMPLETED
        instance.completed_at = now
        instance.due_at = None
    else:
        instance.status = GovernanceInstance.Status.ACTIVE
        instance.completed_at = None
        instance.due_at = (
            now
            + timezone.timedelta(
                days=next_stage.target_duration_days,
            )
        )

    instance.save()

    # ======================================================
    # CRÉATION DE LA TÂCHE DE LA NOUVELLE ÉTAPE
    # ======================================================

    if not next_stage.is_final:
        existing_open_task = (
            GovernanceTask.objects
            .filter(
                instance=instance,
                stage=next_stage,
            )
            .exclude(
                status__in=[
                    GovernanceTask.Status.COMPLETED,
                    GovernanceTask.Status.CANCELLED,
                ],
            )
            .exists()
        )

        if not existing_open_task:
            _create_stage_task(
                instance=instance,
                stage=next_stage,
                actor=actor,
            )

    # ======================================================
    # JOURNALISATION DE LA TRANSITION APPLIQUÉE
    # ======================================================

    create_decision_log(
        instance=instance,
        result=result,
        actor=actor,
        from_stage=from_stage,
        to_stage=next_stage,
        transition=transition,
        application_status=(
            GovernanceDecisionLog
            .ApplicationStatus
            .APPLIED
        ),
        actor_ip_address=actor_ip_address,
        actor_user_agent=actor_user_agent,
    )

    return result


# ==========================================================
# OUTILS INTERNES
# ==========================================================

def _check_transition_permission(
    *,
    transition: GovernanceTransition,
    actor,
) -> None:
    permission = transition.requires_permission.strip()

    if not permission:
        return

    if actor is None or not actor.has_perm(permission):
        raise PermissionDenied(
            "Vous ne disposez pas de la permission requise "
            f"pour exécuter la transition {transition.name}."
        )


def _create_stage_task(
    *,
    instance: GovernanceInstance,
    stage: GovernanceStage,
    actor,
) -> GovernanceTask:
    now = timezone.now()
    assigned_group = stage.responsible_group

    status = (
        GovernanceTask.Status.ASSIGNED
        if assigned_group
        else GovernanceTask.Status.PENDING
    )

    return GovernanceTask.objects.create(
        instance=instance,
        stage=stage,
        title=f"Traiter l’étape : {stage.name}",
        description=(
            stage.instructions
            or stage.description
            or f"Instruction du dossier à l’étape {stage.name}."
        ),
        task_type=_map_stage_to_task_type(stage),
        priority=GovernanceTask.Priority.NORMAL,
        status=status,
        assigned_group=assigned_group,
        assigned_by=actor,
        assigned_at=now if assigned_group else None,
        due_at=(
            now
            + timezone.timedelta(
                days=stage.target_duration_days,
            )
        ),
        is_mandatory=stage.is_mandatory,
    )


def _map_stage_to_task_type(
    stage: GovernanceStage,
) -> str:
    mapping = {
        GovernanceStage.StageType.AUTOMATED:
            GovernanceTask.TaskType.ANALYSIS,
        GovernanceStage.StageType.REVIEW:
            GovernanceTask.TaskType.REVIEW,
        GovernanceStage.StageType.APPROVAL:
            GovernanceTask.TaskType.VALIDATION,
        GovernanceStage.StageType.COMMITTEE:
            GovernanceTask.TaskType.VOTE,
        GovernanceStage.StageType.LEGAL:
            GovernanceTask.TaskType.DOCUMENT,
        GovernanceStage.StageType.EXECUTION:
            GovernanceTask.TaskType.FOLLOW_UP,
        GovernanceStage.StageType.AUDIT:
            GovernanceTask.TaskType.AUDIT,
        GovernanceStage.StageType.FINANCIAL:
            GovernanceTask.TaskType.ANALYSIS,
        GovernanceStage.StageType.CLOSURE:
            GovernanceTask.TaskType.VALIDATION,
    }

    return mapping.get(
        stage.stage_type,
        GovernanceTask.TaskType.OTHER,
    )