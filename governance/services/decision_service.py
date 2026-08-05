"""
Services de décision, d'approbation, de rejet et de vote.
"""


def approve_case(*, instance, actor, comment=""):
    raise NotImplementedError


def reject_case(*, instance, actor, reason):
    raise NotImplementedError


def request_additional_information(*, instance, actor, comment):
    raise NotImplementedError