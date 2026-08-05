"""
Vues du portail de gouvernance YAAYESS.
"""

from .dashboard import governance_dashboard
from .instance_detail import governance_instance_detail
from .instances import governance_instance_list
from .log_detail import governance_decision_log_detail
from .logs import governance_decision_log_list
from .tasks import governance_task_list


__all__ = [
    "governance_dashboard",
    "governance_instance_list",
    "governance_instance_detail",
    "governance_task_list",
    "governance_decision_log_list",
    "governance_decision_log_detail",
]