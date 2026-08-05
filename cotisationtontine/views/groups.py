from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Notification
from accounts.utils import envoyer_invitation
from cotisationtontine.forms import GroupForm
from cotisationtontine.models import (
    ActionLog,
    Cycle,
    EtapeCycle,
    Group,
    GroupMember,
    Versement,
)

@login_required
@transaction.atomic
def ajouter_groupe_view(request):
    """
    CrÃ©ation d'un nouveau groupe par un utilisateur connectÃ© :
    1ï¸âƒ£ CrÃ©ation du groupe avec l'utilisateur comme admin
    2ï¸âƒ£ Ajout de l'admin comme membre
    3ï¸âƒ£ GÃ©nÃ©ration d'un lien d'invitation
    4ï¸âƒ£ Envoi de l'invitation (simulation WhatsApp ou SMS)
    """
    if request.method == "POST":
        form = GroupForm(request.POST)
        if form.is_valid():
            try:
                # âœ… CrÃ©er le groupe
                group = form.save(commit=False)
                group.admin = request.user
                group.save()

                # âœ… Ajoute l'admin comme membre du groupe
                GroupMember.objects.create(
                    group=group,
                    user=request.user,
                    montant=0
                )

                # âœ… CrÃ©e un lien d'invitation sÃ©curisÃ© (utilise le code_invitation du groupe)
                lien_invitation = request.build_absolute_uri(
                    reverse("accounts:inscription_et_rejoindre", args=[str(group.code_invitation)])
                )

                # âœ… Simule l'envoi de l'invitation (WhatsApp ou SMS)
                envoyer_invitation(request.user.phone, lien_invitation)

                # âœ… Message de confirmation
                messages.success(request,
                                 f"Groupe Â« {group.nom} Â» crÃ©Ã© avec succÃ¨s et vous avez Ã©tÃ© ajoutÃ© comme membre.")

                # âœ… Redirection vers le dashboard Tontine
                return redirect("cotisationtontine:dashboard_tontine_simple")

            except Exception as e:
                messages.error(request, f"Erreur lors de la crÃ©ation du groupe: {str(e)}")
    else:
        form = GroupForm()

    return render(
        request,
        "cotisationtontine/ajouter_groupe.html",
        {"form": form, "title": "CrÃ©er un groupe"}
    )

@login_required
def group_list_view(request):

    user = request.user

    if getattr(user, "is_super_admin", False):
        groupes = Group.objects.all().order_by("-date_creation")
    else:
        groupes = (
            Group.objects.filter(
                Q(admin=user) |
                Q(membres__user=user)
            )
            .distinct()
            .order_by("-date_creation")
        )

    # ðŸ”¥ AJOUT IMPORTANT
    is_admin_group = Group.objects.filter(admin=user).exists()

    context = {
        "groupes": groupes,
        "is_admin_group": is_admin_group   # âœ… AJOUT
    }

    return render(
        request,
        "cotisationtontine/group_list.html",
        context
    )

@login_required
def group_detail(request, group_id):

    group = get_object_or_404(Group, id=group_id)

    # ðŸ”” NOTIFICATIONS
    notifications = Notification.objects.order_by('-created_at')[:5]

    # ðŸ”’ ACCÃˆS
    has_access = (
        group.admin_id == request.user.id
        or GroupMember.objects.filter(group=group, user=request.user).exists()
        or getattr(request.user, "is_super_admin", False)
        or request.user.is_superuser
    )

    if not has_access:
        messages.error(request, "âš ï¸ AccÃ¨s refusÃ©.")
        return redirect("cotisationtontine:dashboard_tontine_simple")

    user_is_admin = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or request.user.is_superuser
    )

    # =====================================================
    # ðŸ”¥ VARIABLES
    # =====================================================
    cycle_actuel = group.cycle_numero
    tour_actuel = group.tour_actuel

    # =====================================================
    # ðŸ’³ VERSEMENTS EN ATTENTE
    # =====================================================
    versements_en_attente_liste = []

    if user_is_admin:
        versements_en_attente_liste = (
            Versement.objects
            .filter(
                member__group=group,
                statut="EN_ATTENTE",
                tour=tour_actuel,
                cycle=cycle_actuel  # ðŸ”¥ FIX
            )
            .select_related("member__user")
            .order_by("-date_creation")
        )

    # =====================================================
    # ðŸ“Š MEMBRES
    # =====================================================
    rel_lookup = "versements"

    last_qs = Versement.objects.filter(
        member=OuterRef("pk"),
        statut="VALIDE",
        tour=tour_actuel,
        cycle=cycle_actuel  # ðŸ”¥ FIX
    ).order_by("-date_creation")

    sum_filter = Q(
        **{
            f"{rel_lookup}__statut": "VALIDE",
            f"{rel_lookup}__tour": tour_actuel,
            f"{rel_lookup}__cycle": cycle_actuel,  # ðŸ”¥ FIX
        }
    )

    membres = (
        GroupMember.objects
        .filter(group=group)
        .select_related("user")
        .annotate(
            total_montant=Coalesce(
                Sum(f"{rel_lookup}__montant", filter=sum_filter),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            last_amount=Subquery(last_qs.values("montant")[:1]),
            last_date=Subquery(last_qs.values("date_creation")[:1]),
        )
        .order_by("id")
    )

    # =====================================================
    # ðŸ”„ VERSEMENTS EN ATTENTE PAR MEMBRE
    # =====================================================
    versements_map = {}

    if user_is_admin:
        versements = (
            Versement.objects
            .filter(
                member__group=group,
                statut="EN_ATTENTE",
                tour=tour_actuel,
                cycle=cycle_actuel  # ðŸ”¥ FIX
            )
            .select_related("member")
        )

        for v in versements:
            versements_map[v.member_id] = v

    for m in membres:
        m.versement_en_attente = versements_map.get(m.id)

    # =====================================================
    # ðŸ’° TOTAL DU GROUPE
    # =====================================================
    total_montant = (
        Versement.objects
        .filter(
            member__group=group,
            statut="VALIDE",
            tour=tour_actuel,
            cycle=cycle_actuel  # ðŸ”¥ FIX
        )
        .aggregate(
            total=Coalesce(
                Sum("montant"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )["total"]
    )

    # =====================================================
    # ðŸ“ HISTORIQUE
    # =====================================================
    actions = (
        ActionLog.objects
        .filter(group=group)
        .select_related("user")
        .order_by("-date")[:10]
    )

    # =====================================================
    # ðŸ”— INVITATION
    # =====================================================
    code = str(group.code_invitation or group.invitation_token or group.id)

    invite_url = request.build_absolute_uri(
        reverse("accounts:inscription_et_rejoindre", args=[code])
    )

    if user_is_admin:
        request.session["last_invitation_link"] = invite_url

    # =====================================================
    # ðŸŽ² LOGIQUE CYCLE
    # =====================================================
    membres_actifs = group.membres.filter(actif=True, exit_liste=False)

    gagnants_ids = group.tirages.filter(
        cycle_number=cycle_actuel
    ).values_list("gagnant_id", flat=True)

    membres_restants = membres_actifs.exclude(id__in=gagnants_ids)

    cycle_termine = not membres_restants.exists()

    nb_restants = membres_restants.count()
    total_membres = membres_actifs.count()
    nb_termines = total_membres - nb_restants

    progress = int((nb_termines / total_membres) * 100) if total_membres > 0 else 0

    # =====================================================
    # ðŸ’° HISTORIQUE COMPLET DES PAIEMENTS
    # =====================================================

    versements_list = (
        Versement.objects
        .filter(member__group=group)
        .select_related("member__user")
        .order_by("-date_creation")[:10]  # ðŸ”¥ LIMITATION ICI
    )

    # ðŸ”¥ TOTAL GLOBAL (TOUS LES PAIEMENTS)
    total_global = (
        versements_list.aggregate(
            total=Coalesce(
                Sum("montant"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )["total"]
    )

    # =====================================================
    # ðŸ“¦ CONTEXT
    # =====================================================
    context = {
        "group": group,
        "membres": membres,
        "total_montant": total_montant,
        "admin_user": group.admin,
        "actions": actions,
        "user_is_admin": user_is_admin,
        "invite_url": invite_url,
        "last_invitation_link": request.session.get("last_invitation_link"),
        "versements_en_attente_liste": versements_en_attente_liste,
        "notifications": notifications,

        "cycle_termine": cycle_termine,
        "cycle_actuel": cycle_actuel,
        "tour_actuel": tour_actuel,
        "nb_restants": nb_restants,
        "progress": progress,
        "versements_list": versements_list,
        "total_global": total_global,
    }

    return render(request, "cotisationtontine/group_detail.html", context)


@login_required
@transaction.atomic
def reset_cycle_view(request, group_id):

    group = get_object_or_404(Group, id=group_id)

    # =====================================================
    # ðŸ”’ SÃ‰CURITÃ‰
    # =====================================================
    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "AccÃ¨s non autorisÃ©.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    membres_actifs = group.membres.filter(actif=True, exit_liste=False)
    cycle_actuel = group.cycle_numero

    # =====================================================
    # ðŸ”¥ VÃ‰RIFIER SI CYCLE TERMINÃ‰
    # =====================================================
    gagnants_ids = group.tirages.filter(
        cycle_number=cycle_actuel
    ).values_list("gagnant_id", flat=True)

    membres_restants = membres_actifs.exclude(id__in=gagnants_ids)

    if membres_restants.exists():
        messages.error(
            request,
            "âŒ Impossible de rÃ©initialiser : le cycle n'est pas terminÃ©."
        )
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # =====================================================
    # ðŸ§  1. ARCHIVER LE CYCLE (SANS DOUBLON)
    # =====================================================

    # ðŸ”¥ Ã©viter doublon
    Cycle.objects.filter(group=group, numero=cycle_actuel).delete()

    cycle_archive = Cycle.objects.create(
        group=group,
        numero=cycle_actuel,
        date_debut=group.date_reset or group.date_creation,
        date_fin=timezone.now()
    )

    tirages = group.tirages.filter(
        cycle_number=cycle_actuel
    ).select_related("gagnant__user").order_by("date_tirage")

    for index, tirage in enumerate(tirages, start=1):
        EtapeCycle.objects.create(
            cycle=cycle_archive,
            numero_etape=index,
            date_etape=tirage.date_tirage,
            tirage=tirage
        )

    # =====================================================
    # ðŸ§¹ 2. SUPPRIMER UNIQUEMENT LES TIRAGES
    # =====================================================
    group.tirages.filter(cycle_number=cycle_actuel).delete()

    # ðŸš« NE PAS TOUCHER AUX VERSEMENTS
    # ðŸ‘‰ historique financier conservÃ©

    # =====================================================
    # ðŸ”¥ 3. RESET MEMBRES
    # =====================================================
    membres_actifs.update(
        a_recu=False,
        montant=0
    )

    # =====================================================
    # ðŸ”„ 4. RESET GROUPE
    # =====================================================
    group.cycle_numero += 1
    group.tour_actuel = 1

    group.is_active = True
    group.cycle_termine = False
    group.prochain_gagnant = None

    group.date_reset = timezone.now()

    group.save()

    # =====================================================
    # ðŸ“ 5. LOG
    # =====================================================
    ActionLog.objects.create(
        user=request.user,
        group=group,
        action=f"Reset cycle #{cycle_actuel} â†’ cycle #{group.cycle_numero}"
    )

    # =====================================================
    # âœ… MESSAGE
    # =====================================================
    messages.success(
        request,
        f"âœ… Cycle #{cycle_actuel} archivÃ© avec succÃ¨s. Nouveau cycle #{group.cycle_numero} lancÃ©."
    )

    return redirect("cotisationtontine:group_detail", group_id=group.id)
