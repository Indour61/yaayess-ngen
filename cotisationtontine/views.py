from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from cotisationtontine.models import Group, GroupMember, Versement, ActionLog



from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Group, Versement, ActionLog


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta

from .models import Group, Versement, ActionLog



@login_required
def dashboard_tontine_simple(request):
    """
    Dashboard principal Tontine
    Visible uniquement si l'utilisateur administre un groupe
    """

    user = request.user

    # =====================================================
    # 🔒 Sécurité : vérifier si utilisateur admin d'un groupe
    # =====================================================

    groupes_admin = (
        Group.objects
        .filter(admin=user)
        .prefetch_related("membres")
        .order_by("-date_creation")
    )

    if not groupes_admin.exists():
        messages.warning(
            request,
            "Vous n’êtes administrateur d’aucun groupe."
        )
#        return redirect("accounts:login")
        return render(
            request,
            "cotisationtontine/no_group.html"
        )
    # =====================================================
    # 👥 Groupes où l'utilisateur est membre
    # =====================================================

    groupes_membre = (
        Group.objects
        .filter(membres__user=user)
        .exclude(admin=user)
        .distinct()
    )

    # =====================================================
    # 📝 Dernières actions utilisateur
    # =====================================================

    dernieres_actions = (
        ActionLog.objects
        .filter(user=user)
        .select_related("group")
        .order_by("-date")[:10]
    )

    # =====================================================
    # 💰 Total versements utilisateur
    # =====================================================

    total_versements = (
        Versement.objects
        .filter(member__user=user, statut="VALIDE")
        .aggregate(total=Sum("montant"))
        .get("total") or 0
    )

    # =====================================================
    # 📊 Nombre total groupes utilisateur
    # =====================================================

    total_groupes = (
        Group.objects
        .filter(membres__user=user)
        .distinct()
        .count()
    )

    # =====================================================
    # 📅 Versements récents (30 jours)
    # =====================================================

    date_limite = timezone.now() - timedelta(days=30)

    versements_recents = (
        Versement.objects
        .filter(
            member__user=user,
            date_creation__gte=date_limite
        )
        .select_related("member__group")
        .order_by("-date_creation")[:5]
    )

    # =====================================================
    # 📈 Stats groupes administrés
    # =====================================================

    stats_groupes_admin = (
        Versement.objects
        .filter(member__group__admin=user, statut="VALIDE")
        .values(
            "member__group__id",
            "member__group__nom"
        )
        .annotate(
            versements_total=Sum("montant")
        )
        .order_by("-versements_total")
    )

    # =====================================================
    # 📦 Context
    # =====================================================

    context = {
        "groupes_admin": groupes_admin,
        "groupes_membre": groupes_membre,
        "action_logs": dernieres_actions,  # 🔥 CORRECTION ICI
        "total_versements": total_versements,
        "total_groupes": total_groupes,
        "versements_recents": versements_recents,
        "stats_groupes_admin": stats_groupes_admin,
    }

    return render(
        request,
        "cotisationtontine/dashboard.html",
        context
    )

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.db import transaction, IntegrityError
from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
import requests
from decimal import Decimal

from cotisationtontine.forms import GroupForm, GroupMemberForm, VersementForm
from cotisationtontine.models import Group, GroupMember, Invitation, Versement, ActionLog
from accounts.models import CustomUser
from accounts.utils import envoyer_invitation


@login_required
@transaction.atomic
def ajouter_groupe_view(request):
    """
    Création d'un nouveau groupe par un utilisateur connecté :
    1️⃣ Création du groupe avec l'utilisateur comme admin
    2️⃣ Ajout de l'admin comme membre
    3️⃣ Génération d'un lien d'invitation
    4️⃣ Envoi de l'invitation (simulation WhatsApp ou SMS)
    """
    if request.method == "POST":
        form = GroupForm(request.POST)
        if form.is_valid():
            try:
                # ✅ Créer le groupe
                group = form.save(commit=False)
                group.admin = request.user
                group.save()

                # ✅ Ajoute l'admin comme membre du groupe
                GroupMember.objects.create(
                    group=group,
                    user=request.user,
                    montant=0
                )

                # ✅ Crée un lien d'invitation sécurisé (utilise le code_invitation du groupe)
                lien_invitation = request.build_absolute_uri(
                    reverse("accounts:inscription_et_rejoindre", args=[str(group.code_invitation)])
                )

                # ✅ Simule l'envoi de l'invitation (WhatsApp ou SMS)
                envoyer_invitation(request.user.phone, lien_invitation)

                # ✅ Message de confirmation
                messages.success(request,
                                 f"Groupe « {group.nom} » créé avec succès et vous avez été ajouté comme membre.")

                # ✅ Redirection vers le dashboard Tontine
                return redirect("cotisationtontine:dashboard_tontine_simple")

            except Exception as e:
                messages.error(request, f"Erreur lors de la création du groupe: {str(e)}")
    else:
        form = GroupForm()

    return render(
        request,
        "cotisationtontine/ajouter_groupe.html",
        {"form": form, "title": "Créer un groupe"}
    )

@login_required
@transaction.atomic
def ajouter_membre_view(request, group_id):

    group = get_object_or_404(Group, id=group_id)

    # 🔒 1. Sécurité admin
    if group.admin != request.user:
        messages.error(request, "⚠️ Vous n'avez pas les droits pour ajouter un membre à ce groupe.")
        return redirect("cotisationtontine:dashboard_tontine_simple")

    # 🔒 2. BLOQUAGE MÉTIER (TRÈS IMPORTANT)
    if group.tirage_effectue:
        messages.error(request, "🚫 Impossible d'ajouter un membre : le cycle est déjà en cours.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    if group.cycle_termine:
        messages.error(request, "🚫 Cycle terminé. Veuillez réinitialiser avant d'ajouter un membre.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    if request.method == "POST":
        form = GroupMemberForm(request.POST)

        if form.is_valid():
            phone = form.cleaned_data.get("phone")
            nom = form.cleaned_data.get("nom")

            # 🔒 3. VALIDATION NUMÉRO
            if not phone:
                messages.error(request, "Numéro invalide.")
                return redirect(request.path)

            # 🔒 4. Création ou récupération utilisateur
            user, created_user = CustomUser.objects.get_or_create(
                phone=phone,
                defaults={"nom": nom or f"Utilisateur {phone}"}
            )

            # 🔔 Alerte si conflit nom
            if not created_user and user.nom != nom:
                messages.warning(
                    request,
                    f"⚠️ Ce numéro appartient déjà à {user.nom}. Nom fourni ignoré."
                )
                nom = user.nom

            # 🔒 5. Vérifier doublon dans groupe
            if GroupMember.objects.filter(group=group, user=user).exists():
                messages.info(request, f"ℹ️ {user.nom} est déjà membre du groupe.")
                return redirect("cotisationtontine:group_detail", group_id=group.id)

            # 🔒 6. Détection noms identiques
            existing = GroupMember.objects.filter(
                group=group,
                user__nom=nom
            ).exclude(user__phone=phone)

            alias = None
            if existing.exists():
                messages.warning(
                    request,
                    f"⚠️ Le nom '{nom}' existe déjà. Un alias sera utilisé."
                )
                alias = f"{nom} ({phone})"

            # 🔥 7. CRÉATION MEMBRE
            group_member = GroupMember.objects.create(
                group=group,
                user=user,
                montant=0,
                alias=alias
            )

            # 🔔 Message
            display_name = alias if alias else user.nom
            messages.success(request, f"✅ {display_name} ajouté avec succès.")

            return redirect("cotisationtontine:group_detail", group_id=group.id)

    else:
        form = GroupMemberForm()

    return render(request, "cotisationtontine/ajouter_membre.html", {
        "group": group,
        "form": form
    })

from django.db.models import Q  # Ajoutez cette importation en haut du fichier

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Q
from cotisationtontine.models import Group


from django.db.models import Q

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from cotisationtontine.models import Group, GroupMember

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

    # 🔥 AJOUT IMPORTANT
    is_admin_group = Group.objects.filter(admin=user).exists()

    context = {
        "groupes": groupes,
        "is_admin_group": is_admin_group   # ✅ AJOUT
    }

    return render(
        request,
        "cotisationtontine/group_list.html",
        context
    )


from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db.models import Sum, Q, Value, DecimalField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from .models import Group, GroupMember, Versement, ActionLog


# =====================================================
# 📊 Dashboard simple
# =====================================================

@login_required
def dashboard(request):

    action_logs = (
        ActionLog.objects
        .filter(user=request.user)
        .order_by("-date")[:10]
    )

    context = {
        "action_logs": action_logs
    }

    return render(
        request,
        "cotisationtontine/dashboard.html",
        context
    )


# =====================================================
# 👥 Détail d’un groupe
# =====================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from django.db.models import Q, Sum, Value, DecimalField, Subquery, OuterRef
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from accounts.models import Notification
from .models import Group, GroupMember, Versement, ActionLog


@login_required
def group_detail(request, group_id):

    group = get_object_or_404(Group, id=group_id)

    # 🔔 NOTIFICATIONS
    notifications = Notification.objects.order_by('-created_at')[:5]

    # 🔒 ACCÈS
    has_access = (
        group.admin_id == request.user.id
        or GroupMember.objects.filter(group=group, user=request.user).exists()
        or getattr(request.user, "is_super_admin", False)
        or request.user.is_superuser
    )

    if not has_access:
        messages.error(request, "⚠️ Accès refusé.")
        return redirect("cotisationtontine:dashboard_tontine_simple")

    user_is_admin = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or request.user.is_superuser
    )

    # =====================================================
    # 🔥 VARIABLES
    # =====================================================
    cycle_actuel = group.cycle_numero
    tour_actuel = group.tour_actuel

    # =====================================================
    # 💳 VERSEMENTS EN ATTENTE
    # =====================================================
    versements_en_attente_liste = []

    if user_is_admin:
        versements_en_attente_liste = (
            Versement.objects
            .filter(
                member__group=group,
                statut="EN_ATTENTE",
                tour=tour_actuel,
                cycle=cycle_actuel  # 🔥 FIX
            )
            .select_related("member__user")
            .order_by("-date_creation")
        )

    # =====================================================
    # 📊 MEMBRES
    # =====================================================
    rel_lookup = "versements"

    last_qs = Versement.objects.filter(
        member=OuterRef("pk"),
        statut="VALIDE",
        tour=tour_actuel,
        cycle=cycle_actuel  # 🔥 FIX
    ).order_by("-date_creation")

    sum_filter = Q(
        **{
            f"{rel_lookup}__statut": "VALIDE",
            f"{rel_lookup}__tour": tour_actuel,
            f"{rel_lookup}__cycle": cycle_actuel,  # 🔥 FIX
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
    # 🔄 VERSEMENTS EN ATTENTE PAR MEMBRE
    # =====================================================
    versements_map = {}

    if user_is_admin:
        versements = (
            Versement.objects
            .filter(
                member__group=group,
                statut="EN_ATTENTE",
                tour=tour_actuel,
                cycle=cycle_actuel  # 🔥 FIX
            )
            .select_related("member")
        )

        for v in versements:
            versements_map[v.member_id] = v

    for m in membres:
        m.versement_en_attente = versements_map.get(m.id)

    # =====================================================
    # 💰 TOTAL DU GROUPE
    # =====================================================
    total_montant = (
        Versement.objects
        .filter(
            member__group=group,
            statut="VALIDE",
            tour=tour_actuel,
            cycle=cycle_actuel  # 🔥 FIX
        )
        .aggregate(
            total=Coalesce(
                Sum("montant"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )["total"]
    )

    # =====================================================
    # 📝 HISTORIQUE
    # =====================================================
    actions = (
        ActionLog.objects
        .filter(group=group)
        .select_related("user")
        .order_by("-date")[:10]
    )

    # =====================================================
    # 🔗 INVITATION
    # =====================================================
    code = str(group.code_invitation or group.invitation_token or group.id)

    invite_url = request.build_absolute_uri(
        reverse("accounts:inscription_et_rejoindre", args=[code])
    )

    if user_is_admin:
        request.session["last_invitation_link"] = invite_url

    # =====================================================
    # 🎲 LOGIQUE CYCLE
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
    # 💰 HISTORIQUE COMPLET DES PAIEMENTS
    # =====================================================

    versements_list = (
        Versement.objects
        .filter(member__group=group)
        .select_related("member__user")
        .order_by("-date_creation")[:10]  # 🔥 LIMITATION ICI
    )

    # 🔥 TOTAL GLOBAL (TOUS LES PAIEMENTS)
    total_global = (
        versements_list.aggregate(
            total=Coalesce(
                Sum("montant"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )["total"]
    )

    # =====================================================
    # 📦 CONTEXT
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

# views.py
import os
import json
from decimal import Decimal, ROUND_HALF_UP
import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

#from .models import GroupMember, Versement


from decimal import Decimal, ROUND_HALF_UP
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

# ==========================================
# DECLARATION VERSEMENT CAISSE
# ==========================================
from decimal import Decimal, ROUND_HALF_UP
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib import messages

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db.models import Sum
from decimal import Decimal, ROUND_HALF_UP

from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db.models import Sum

from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from cotisationtontine.models import GroupMember, Versement


@login_required
@transaction.atomic
def initier_versement(request, member_id):

    member = get_object_or_404(
        GroupMember.objects.select_related("group", "user"),
        id=member_id
    )

    group = member.group
    group.refresh_from_db()

    # =====================================================
    # 🔒 SÉCURITÉ
    # =====================================================

    user_is_admin = (
        request.user == group.admin
        or request.user.is_superuser
    )

    if not user_is_admin and request.user != member.user:
        messages.error(request, "❌ Vous ne pouvez verser que pour vous-même.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # =====================================================
    # 🔥 VÉRIFIER SI CYCLE TERMINÉ
    # =====================================================

    membres_actifs = group.membres.filter(actif=True, exit_liste=False)

    gagnants_ids = group.tirages.filter(
        cycle_number=group.cycle_numero
    ).values_list("gagnant_id", flat=True)

    membres_restants = membres_actifs.exclude(id__in=gagnants_ids)

    if not membres_restants.exists():
        messages.error(request, "❌ Le cycle est terminé. Veuillez réinitialiser.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # =====================================================
    # 🔥 BLOQUER DOUBLE PAIEMENT VALIDÉ
    # =====================================================

    # 🔥 TOTAL déjà versé (VALIDÉ uniquement)
    total_valide = Versement.objects.filter(
        member=member,
        statut="VALIDE",
        cycle=group.cycle_numero,
        tour=group.tour_actuel
    ).aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    # 🔥 Montant max à atteindre
    montant_max = group.montant_base or Decimal("0")

    # 🔥 Calcul du reste
    reste = montant_max - total_valide

    # 🔒 Bloquer si déjà complet
    if reste <= 0:
        messages.success(
            request,
            f"✅ Vous avez déjà complété le paiement pour le tour {group.tour_actuel}."
        )
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # =====================================================
    # 🔥 CALCUL DU RESTE À PAYER
    # =====================================================

    versements_tour = member.versements.filter(
        statut__in=["EN_ATTENTE", "VALIDE"],
        tour=group.tour_actuel,
        cycle=group.cycle_numero
    )

    total_actuel = versements_tour.aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    montant_max = group.montant_base or Decimal("0")
    reste = montant_max - total_actuel

    # =====================================================
    # GET → AFFICHAGE PAGE
    # =====================================================

    if request.method == "GET":

        frais = (reste * Decimal("0.02")).quantize(Decimal("1"))
        total = reste + frais

        return render(
            request,
            "cotisationtontine/initier_versement.html",
            {
                "member": member,
                "group": group,
                "montant_base": montant_max,
                "reste": reste,
                "frais": frais,
                "total": total,
                "tour": group.tour_actuel
            }
        )

    # =====================================================
    # POST → TRAITEMENT
    # =====================================================

    montant_raw = (request.POST.get("montant") or "").replace(",", ".").strip()
    methode = request.POST.get("methode")
    preuve = request.FILES.get("preuve")

    # 🔒 validation montant
    try:
        montant = Decimal(montant_raw)
    except Exception:
        messages.error(request, "❌ Montant invalide.")
        return redirect("cotisationtontine:initier_versement", member_id=member_id)

    if montant <= 0:
        messages.error(request, "❌ Le montant doit être supérieur à 0.")
        return redirect("cotisationtontine:initier_versement", member_id=member_id)

    montant = montant.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # 🔒 déjà complet
    if reste <= 0:
        messages.warning(request, "✅ Montant déjà atteint pour ce tour.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # 🔒 dépassement
    if montant > reste:
        messages.error(request, f"❌ Dépassement ! Il reste {reste} FCFA.")
        return redirect("cotisationtontine:initier_versement", member_id=member_id)

    # =====================================================
    # 🔒 VALIDATION MÉTHODE
    # =====================================================

    if methode not in ["WAVE", "OM", "CAISSE"]:
        messages.error(request, "❌ Méthode de paiement invalide.")
        return redirect("cotisationtontine:initier_versement", member_id=member_id)

    # =====================================================
    # 💰 FRAIS
    # =====================================================

    frais = (montant * Decimal("0.02")).quantize(Decimal("1"))

    # =====================================================
    # 💰 CRÉATION VERSEMENT
    # =====================================================

    versement = Versement.objects.create(
        member=member,
        montant=montant,
        frais=frais,
        methode=methode,
        preuve=preuve,
        statut="EN_ATTENTE",
        tour=group.tour_actuel,
        cycle=group.cycle_numero
    )

    print("✅ VERSEMENT CRÉÉ ID =", versement.id)

    # =====================================================
    # 🔥 MESSAGE UX
    # =====================================================

    messages.success(
        request,
        f"⏳ Paiement de {montant} FCFA envoyé via {methode}. En attente de validation."
    )

    return redirect("cotisationtontine:group_detail", group_id=group.id)

# ==========================================
# VALIDATION ADMIN
# ==========================================

@login_required
@transaction.atomic
def valider_versement(request, versement_id):

    versement = get_object_or_404(
        Versement.objects.select_related("member__group"),
        id=versement_id
    )
    group = versement.member.group

    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "Accès refusé.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    versement.statut = "VALIDE"
    versement.valide_par = request.user
    versement.date_validation = timezone.now()
    versement.save()

    messages.success(request, "Versement validé avec succès.")
    return redirect("cotisationtontine:group_detail", group_id=group.id)


# ==========================================
# REFUSER VERSEMENT
# ==========================================

@login_required
@transaction.atomic
def refuser_versement(request, versement_id):

    versement = get_object_or_404(
        Versement.objects.select_related("member__group"),
        id=versement_id
    )
    group = versement.member.group

    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "Accès refusé.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    versement.statut = "REFUSE"
    versement.valide_par = request.user
    versement.date_validation = timezone.now()
    versement.save()

    messages.success(request, "Versement refusé.")
    return redirect("cotisationtontine:group_detail", group_id=group.id)


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required


from .models import Group, GroupMember
from .forms import GroupMemberForm

@login_required
def editer_membre_view(request, group_id, membre_id):
    group = get_object_or_404(Group, id=group_id)
    membre = get_object_or_404(GroupMember, id=membre_id, group=group)

    # 🔒 Sécurité
    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "Accès non autorisé.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    if request.method == "POST":
        form = GroupMemberForm(request.POST, instance=membre)
        if form.is_valid():
            form.save()
            messages.success(request, "Membre modifié avec succès ✅")
            return redirect("cotisationtontine:group_detail", group_id=group.id)
    else:
        form = GroupMemberForm(instance=membre)

    return render(request, "cotisationtontine/editer_membre.html", {
        "form": form,
        "group": group,
        "membre": membre
    })

@login_required
@transaction.atomic
def supprimer_membre_view(request, group_id, membre_id):

    group = get_object_or_404(Group, id=group_id)
    membre = get_object_or_404(GroupMember, id=membre_id, group=group)

    # 🔒 1. Sécurité admin
    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "⛔ Accès non autorisé.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # 🔒 2. BLOQUAGE SI CYCLE EN COURS
    if group.tirage_effectue:
        messages.error(request, "🚫 Impossible de supprimer un membre : le cycle est en cours.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # 🔒 3. BLOQUAGE SI CYCLE TERMINÉ
    if group.cycle_termine:
        messages.error(request, "🚫 Cycle terminé. Veuillez réinitialiser avant toute modification.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # 🔒 4. BLOQUAGE SI LE MEMBRE A DÉJÀ REÇU
    if membre.a_recu:
        messages.error(request, "🚫 Impossible : ce membre a déjà reçu la cagnotte.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # 🔒 5. BLOQUAGE SI LE MEMBRE A COTISÉ
    if membre.montant > 0:
        messages.error(request, "🚫 Impossible : ce membre a déjà cotisé.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # 🔒 6. PROTECTION MINIMUM (optionnel mais très important)
    total_membres = group.membres.filter(actif=True).count()
    if total_membres <= 1:
        messages.error(request, "🚫 Impossible de supprimer le dernier membre du groupe.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # 🔥 7. SUPPRESSION
    if request.method == "POST":
        membre.delete()
        messages.success(request, "✅ Membre supprimé avec succès.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    return render(request, "cotisationtontine/confirmer_suppression.html", {
        "membre": membre,
        "group": group
    })


import random

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Group, Tirage, Versement


@login_required
@transaction.atomic
def tirage_au_sort_view(request, group_id):
    """
    Effectue le tirage d'un bénéficiaire pour le tour courant.

    Le montant attribué au gagnant correspond uniquement à la somme
    des versements validés du cycle et du tour en cours.
    """

    # =====================================================
    # VERROUILLAGE DU GROUPE
    # Empêche deux tirages simultanés sur le même groupe.
    # =====================================================

    group = get_object_or_404(
        Group.objects.select_for_update(),
        id=group_id,
    )

    # =====================================================
    # CONTRÔLE DES PERMISSIONS
    # =====================================================

    if request.user != group.admin and not request.user.is_superuser:
        return JsonResponse(
            {"error": "Accès non autorisé."},
            status=403,
        )

    membres_actifs = group.membres.filter(
        actif=True,
        exit_liste=False,
    )

    if not membres_actifs.exists():
        return JsonResponse(
            {"error": "Aucun membre actif dans ce groupe."},
            status=400,
        )

    # =====================================================
    # CYCLE COURANT
    # =====================================================

    cycle_en_cours = group.cycle_numero

    gagnants_ids = (
        group.tirages
        .filter(cycle_number=cycle_en_cours)
        .values_list("gagnant_id", flat=True)
    )

    membres_restants = membres_actifs.exclude(
        id__in=gagnants_ids,
    )

    # =====================================================
    # CYCLE DÉJÀ TERMINÉ
    # =====================================================

    if not membres_restants.exists():
        group.cycle_termine = True
        group.is_active = False

        group.save(
            update_fields=[
                "cycle_termine",
                "is_active",
            ]
        )

        if group.auto_reset:
            group.reset_cycle()

            return JsonResponse(
                {
                    "reset": True,
                    "message": (
                        "Le cycle précédent est terminé. "
                        "Un nouveau cycle a été démarré."
                    ),
                    "cycle": group.cycle_numero,
                }
            )

        return JsonResponse(
            {
                "cycle_termine": True,
                "message": (
                    "Le cycle est terminé. "
                    "Un nouveau cycle doit être démarré."
                ),
                "cycle": cycle_en_cours,
            },
            status=400,
        )

    # =====================================================
    # TOUR COURANT
    # =====================================================

    tour_en_cours = group.tour_actuel

    # =====================================================
    # FILTRE STRICT :
    # GROUPE + CYCLE + TOUR + STATUT VALIDÉ
    # =====================================================

    versements_valides_q = Q(
        member__group=group,
        statut="VALIDE",
        cycle=cycle_en_cours,
        tour=tour_en_cours,
    )

    # =====================================================
    # VÉRIFIER QUE TOUS LES MEMBRES ONT PAYÉ
    # =====================================================

    membres_non_a_jour = []

    for membre in membres_actifs:
        a_paye = Versement.objects.filter(
            versements_valides_q,
            member=membre,
        ).exists()

        if not a_paye:
            nom_membre = (
                membre.alias
                or getattr(membre.user, "username", "")
                or getattr(membre.user, "phone", "")
                or "Membre"
            )

            membres_non_a_jour.append(nom_membre)

    if membres_non_a_jour:
        return JsonResponse(
            {
                "error": (
                    "Tous les membres doivent avoir un versement "
                    "validé avant le tirage."
                ),
                "non_payes": membres_non_a_jour,
            },
            status=400,
        )

    # =====================================================
    # VÉRIFIER LES VERSEMENTS EN ATTENTE
    # Il faut également filtrer par cycle.
    # =====================================================

    versements_en_attente = Versement.objects.filter(
        member__group=group,
        statut="EN_ATTENTE",
        cycle=cycle_en_cours,
        tour=tour_en_cours,
    )

    if versements_en_attente.exists():
        return JsonResponse(
            {
                "error": (
                    "Tous les versements du cycle et du tour en cours "
                    "doivent être validés avant le tirage."
                )
            },
            status=400,
        )

    # =====================================================
    # MEMBRES ÉLIGIBLES
    # =====================================================

    membres_eligibles = list(membres_restants)

    if not membres_eligibles:
        return JsonResponse(
            {"error": "Aucun membre éligible pour ce tirage."},
            status=400,
        )

    # =====================================================
    # CALCUL DU MONTANT DU TOUR
    # =====================================================

    montant_total = (
        Versement.objects
        .filter(versements_valides_q)
        .aggregate(total=Sum("montant"))
        .get("total")
        or 0
    )

    if montant_total <= 0:
        return JsonResponse(
            {
                "error": (
                    "Le montant total des versements validés "
                    "du tour est nul."
                )
            },
            status=400,
        )

    # =====================================================
    # TIRAGE
    # =====================================================

    gagnant = random.choice(membres_eligibles)

    # =====================================================
    # ENREGISTREMENT DU TIRAGE
    # Le montant est sauvegardé avant le passage au tour suivant.
    # =====================================================

    tirage = Tirage.objects.create(
        group=group,
        gagnant=gagnant,
        montant=montant_total,
        cycle_number=cycle_en_cours,
        tour=tour_en_cours,
    )

    # =====================================================
    # MARQUER LE GAGNANT
    # =====================================================

    gagnant.a_recu = True
    gagnant.save(update_fields=["a_recu"])

    # =====================================================
    # MÉMORISER LE DERNIER GAGNANT
    # =====================================================

    group.prochain_gagnant = gagnant
    group.save(update_fields=["prochain_gagnant"])

    # =====================================================
    # PASSAGE AU TOUR SUIVANT
    # =====================================================

    group.reset_apres_tirage()

    # =====================================================
    # VÉRIFIER SI LE CYCLE VIENT DE SE TERMINER
    # =====================================================

    gagnants_ids = (
        group.tirages
        .filter(cycle_number=cycle_en_cours)
        .values_list("gagnant_id", flat=True)
    )

    membres_restants_apres_tirage = membres_actifs.exclude(
        id__in=gagnants_ids,
    )

    cycle_termine = not membres_restants_apres_tirage.exists()

    if cycle_termine:
        group.cycle_termine = True
        group.is_active = False

        group.save(
            update_fields=[
                "cycle_termine",
                "is_active",
            ]
        )

    # =====================================================
    # NOM DU GAGNANT
    # =====================================================

    nom_gagnant = (
        gagnant.alias
        or getattr(gagnant.user, "username", "")
        or getattr(gagnant.user, "phone", "")
        or "Membre"
    )

    # =====================================================
    # RÉPONSE
    # =====================================================

    return JsonResponse(
        {
            "success": True,
            "tirage_id": tirage.id,
            "gagnant": nom_gagnant,
            "montant": montant_total,
            "cycle": cycle_en_cours,
            "tour": tour_en_cours,
            "cycle_termine": cycle_termine,
            "membres_restants": membres_restants_apres_tirage.count(),
        }
    )

from django.db.models import Sum, Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404

def tirage_resultat_view(request, group_id, token=None):

    group = get_object_or_404(Group, id=group_id)

    # -------------------------------------------------
    # 🔐 SÉCURITÉ ACCÈS
    # -------------------------------------------------
    is_member = False

    if request.user.is_authenticated:
        is_member = group.membres.filter(user=request.user).exists()

    if not is_member:
        if not token or str(getattr(group, "access_token", "")) != str(token):
            return HttpResponseForbidden("❌ Accès refusé")

    # -------------------------------------------------
    # 📊 TIRAGES
    # -------------------------------------------------
    tirages = (
        group.tirages
        .select_related("gagnant__user")
        .order_by("-date_tirage")
    )

    dernier_tirage = tirages.first()

    gagnant = None
    montant_total = 0
    cycle_actuel = group.cycle_numero
    tour_affiche = group.tour_actuel

    # -------------------------------------------------
    # 🔥 UTILISER LE DERNIER TIRAGE (CORRECTION CLÉ)
    # -------------------------------------------------
    if dernier_tirage:
        gagnant = dernier_tirage.gagnant
        cycle_actuel = dernier_tirage.cycle_number or 1

        # 🔥 LE BON MONTANT
        montant_total = dernier_tirage.montant

        # 🔥 LE BON TOUR
        tour_affiche = dernier_tirage.tour

    # -------------------------------------------------
    # 👥 MEMBRES
    # -------------------------------------------------
    membres_actifs = group.membres.filter(actif=True, exit_liste=False)

    gagnants_ids = tirages.filter(
        cycle_number=cycle_actuel
    ).values_list("gagnant_id", flat=True)

    membres_restants = membres_actifs.exclude(id__in=gagnants_ids)

    # -------------------------------------------------
    # 🎯 ÉTAT DU CYCLE
    # -------------------------------------------------
    cycle_termine = not membres_restants.exists()
    tirage_possible = membres_restants.exists()

    # 📊 progression
    total = membres_actifs.count()
    restants = membres_restants.count()
    termines = total - restants

    progress = int((termines / total) * 100) if total > 0 else 0

    # -------------------------------------------------
    # 📦 CONTEXT
    # -------------------------------------------------
    context = {
        "group": group,
        "tirages": tirages,
        "gagnant": gagnant,
        "montant_total": montant_total,
        "tirage_possible": tirage_possible,
        "cycle_actuel": cycle_actuel,
        "cycle_termine": cycle_termine,
        "nb_restants": restants,
        "progress": progress,

        # 🔥 IMPORTANT
        "tour_affiche": tour_affiche,
    }

    return render(
        request,
        "cotisationtontine/tirage_resultat.html",
        context
    )

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Group

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Group


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

# =====================================================
# MEMBRES ÉLIGIBLES POUR TIRAGE
# =====================================================

def membres_eligibles_pour_tirage(group):
    """
    Retourne les membres actifs éligibles au tirage.
    Exclut les membres ayant déjà gagné dans le cycle courant.
    """

    # Membres actifs
    membres_actifs = group.membres.filter(
        actif=True,
        exit_liste=False
    )

    if not membres_actifs.exists():
        return membres_actifs  # vide

    # Membres ayant déjà gagné
    gagnants_ids = group.tirages.values_list(
        "gagnant_id",
        flat=True
    )

    membres_restants = membres_actifs.exclude(
        id__in=gagnants_ids
    )

    # 🎯 Si tout le monde a gagné → nouveau cycle
    if not membres_restants.exists():
        return membres_actifs

    return membres_restants


from django.db import transaction
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

from cotisationtontine.models import Group, Cycle, EtapeCycle, ActionLog


@login_required
@transaction.atomic
def reset_cycle_view(request, group_id):

    group = get_object_or_404(Group, id=group_id)

    # =====================================================
    # 🔒 SÉCURITÉ
    # =====================================================
    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "Accès non autorisé.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    membres_actifs = group.membres.filter(actif=True, exit_liste=False)
    cycle_actuel = group.cycle_numero

    # =====================================================
    # 🔥 VÉRIFIER SI CYCLE TERMINÉ
    # =====================================================
    gagnants_ids = group.tirages.filter(
        cycle_number=cycle_actuel
    ).values_list("gagnant_id", flat=True)

    membres_restants = membres_actifs.exclude(id__in=gagnants_ids)

    if membres_restants.exists():
        messages.error(
            request,
            "❌ Impossible de réinitialiser : le cycle n'est pas terminé."
        )
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # =====================================================
    # 🧠 1. ARCHIVER LE CYCLE (SANS DOUBLON)
    # =====================================================

    # 🔥 éviter doublon
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
    # 🧹 2. SUPPRIMER UNIQUEMENT LES TIRAGES
    # =====================================================
    group.tirages.filter(cycle_number=cycle_actuel).delete()

    # 🚫 NE PAS TOUCHER AUX VERSEMENTS
    # 👉 historique financier conservé

    # =====================================================
    # 🔥 3. RESET MEMBRES
    # =====================================================
    membres_actifs.update(
        a_recu=False,
        montant=0
    )

    # =====================================================
    # 🔄 4. RESET GROUPE
    # =====================================================
    group.cycle_numero += 1
    group.tour_actuel = 1

    group.is_active = True
    group.cycle_termine = False
    group.prochain_gagnant = None

    group.date_reset = timezone.now()

    group.save()

    # =====================================================
    # 📝 5. LOG
    # =====================================================
    ActionLog.objects.create(
        user=request.user,
        group=group,
        action=f"Reset cycle #{cycle_actuel} → cycle #{group.cycle_numero}"
    )

    # =====================================================
    # ✅ MESSAGE
    # =====================================================
    messages.success(
        request,
        f"✅ Cycle #{cycle_actuel} archivé avec succès. Nouveau cycle #{group.cycle_numero} lancé."
    )

    return redirect("cotisationtontine:group_detail", group_id=group.id)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from .models import Group, GroupMember, Versement


class GroupDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, group_id):

        group = get_object_or_404(Group, id=group_id)

        # 🔒 Vérification accès
        has_access = (
            group.admin_id == request.user.id
            or GroupMember.objects.filter(group=group, user=request.user).exists()
            or request.user.is_superuser
        )

        if not has_access:
            return Response({"error": "Accès refusé"}, status=403)

        membres = GroupMember.objects.filter(group=group).select_related("user")

        membres_data = []
        for membre in membres:
            total = (
                Versement.objects
                .filter(member=membre, statut="VALIDE")
                .aggregate(total=Sum("montant"))["total"] or 0
            )

            membres_data.append({
                "id": membre.id,
                "nom": membre.user.nom,
                "telephone": membre.user.phone,
                "total_verse": total
            })

        total_group = (
            Versement.objects
            .filter(member__group=group, statut="VALIDE")
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        return Response({
            "id": group.id,
            "nom": group.nom,
            "montant_base": group.montant,
            "total_cotise": total_group,
            "membres": membres_data,
            "is_admin": request.user == group.admin
        })



class MyGroupAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        group = Group.objects.filter(admin=request.user).first()

        if not group:
            return Response({"has_group": False})

        return Response({
            "has_group": True,
            "group_id": group.id
        })
