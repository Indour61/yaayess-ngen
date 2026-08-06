from .api import GroupDetailAPIView, MyGroupAPIView
from .dashboards import dashboard, dashboard_tontine_simple
from .draws import (
    membres_eligibles_pour_tirage,
    tirage_au_sort_view,
    tirage_resultat_view,
)
from .groups import (
    ajouter_groupe_view,
    group_detail,
    group_list_view,
    reset_cycle_view,
)
from .history import historique_actions_view, historique_cycles_view
from .members import (
    ajouter_membre_view,
    editer_membre_view,
    supprimer_membre_view,
)
from .payments import (
    initier_versement,
    refuser_versement,
    valider_versement,
)


from .paydunya import (
    paydunya_callback,
    paydunya_cancel,
    paydunya_initier,
    paydunya_return,
)