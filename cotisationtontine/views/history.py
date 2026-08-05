from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from cotisationtontine.models import ActionLog, Group

@login_required
def historique_cycles_view(request, group_id):
    """
    Historique basé sur les tirages (solution actuelle)
    """

    group = get_object_or_404(Group, id=group_id)

    # 🔒 Sécurité
    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "Accès non autorisé.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # ✅ UTILISE tirages (PAS cycles)
    tirages_list = (
        group.tirages
        .select_related("gagnant__user")
        .order_by("-date_tirage")
    )

    # 📄 Pagination
    paginator = Paginator(tirages_list, 10)
    page_number = request.GET.get("page")
    tirages = paginator.get_page(page_number)

    context = {
        "group": group,
        "tirages": tirages,
        "total_tirages": tirages_list.count(),
    }

    return render(
        request,
        "cotisationtontine/historique_cycles.html",
        context
    )

from django.core.paginator import Paginator
from django.db.models import Count, Q

@login_required
def historique_actions_view(request):
    """
    Historique global avec filtres + stats + pagination
    """

    if not request.user.is_superuser:
        messages.error(request, "Accès réservé à l’administrateur.")
        return redirect("cotisationtontine:dashboard_tontine_simple")

    logs = ActionLog.objects.select_related("user", "group").order_by("-date")

    # 🔍 FILTRES
    action_type = request.GET.get("action_type")
    group_id = request.GET.get("group")

    if action_type:
        logs = logs.filter(action_type=action_type)

    if group_id:
        logs = logs.filter(group_id=group_id)

    # 📄 Pagination
    paginator = Paginator(logs, 20)
    page_number = request.GET.get("page")
    logs = paginator.get_page(page_number)

    # 📊 STATS
    total_logs = logs.paginator.count

    actions_par_type = (
        ActionLog.objects.values("action_type")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    context = {
        "logs": logs,
        "total_logs": total_logs,
        "actions_par_type": actions_par_type,
        "selected_action": action_type,
        "selected_group": group_id,
    }

    return render(request, "cotisationtontine/historique_actions.html", context)
