"""
Services métier du moteur de gouvernance.

Les fonctions seront implémentées après la création des modèles.
"""


def start_workflow(*, project, started_by):
    raise NotImplementedError(
        "Le moteur de workflow sera implémenté après les modèles."
    )


def advance_workflow(*, instance, actor, decision=None):
    raise NotImplementedError(
        "La progression du workflow sera implémentée après les modèles."
    )


def assign_task(*, instance, stage, assigned_to=None):
    raise NotImplementedError(
        "L'affectation des tâches sera implémentée après les modèles."
    )