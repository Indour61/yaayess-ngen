"""
Services de notification du moteur de gouvernance.
"""


def notify_task_assignment(*, task):
    raise NotImplementedError


def notify_stage_change(*, instance):
    raise NotImplementedError


def notify_decision(*, decision):
    raise NotImplementedError