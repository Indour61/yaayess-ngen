from decimal import Decimal, ROUND_HALF_UP

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import (
    DecimalField,
    Exists,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import Notification
from epargnecredit.forms import GroupForm
from epargnecredit.models import (
    ActionLog,
    Group,
    GroupMember,
    PretDemande,
    Versement,
)
from epargnecredit.utils import envoyer_invitation


# ==========================================================
# Liste des groupes
# ==========================================================

@login_required
def group_list_view(request):
    """
    Affiche les groupes accessibles à l'utilisateur.

    - Le super administrateur voit tous les groupes.
    - Les autres utilisateurs voient les groupes qu'ils administrent
      ou ceux dont ils sont membres.
    """

    if (
        getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    ):
        groupes = (
            Group.objects
            .select_related("admin", "parent_group")
            .all()
            .order_by("-date_creation")
        )
    else:
        groupes = (
            Group.objects
            .select_related("admin", "parent_group")
            .filter(
                Q(admin=request.user)
                | Q(membres_ec=request.user)
            )
            .distinct()
            .order_by("-date_creation")
        )

    return render(
        request,
        "epargnecredit/group_list.html",
        {"groupes": groupes},
    )


# ==========================================================
# Détail d'un groupe
# ==========================================================

@login_required
def group_detail(request, group_id):
    """
    Affiche le détail d'un groupe d'épargne.

    La vue calcule notamment :
    - le total des cotisations ;
    - l'encours des prêts ;
    - la caisse disponible ;
    - le total des intérêts ;
    - le total des pénalités ;
    - le total général.
    """

    group = get_object_or_404(
        Group.objects.select_related("admin", "parent_group"),
        id=group_id,
    )

    # ======================================================
    # Vérification de l'accès
    # ======================================================

    has_access = (
        group.admin_id == request.user.id
        or GroupMember.objects.filter(
            group=group,
            user=request.user,
            actif=True,
        ).exists()
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_access:
        messages.error(
            request,
            "⚠️ Vous n'avez pas accès à ce groupe.",
        )
        return redirect("epargnecredit:group_list")

    # ======================================================
    # Notifications récentes
    # ======================================================

    notifications = (
        Notification.objects
        .order_by("-created_at")[:5]
    )

    # ======================================================
    # Groupe de remboursement associé
    # ======================================================

    remb_group = None

    if (
        not group.is_remboursement
        and hasattr(group, "get_remboursement_group")
    ):
        remb_group = group.get_remboursement_group()

    # ======================================================
    # Sous-requête : dernier versement validé
    # ======================================================

    last_qs = Versement.objects.filter(
        member=OuterRef("pk"),
        statut="VALIDE",
    )

    if group.date_reset:
        last_qs = last_qs.filter(
            date_creation__gte=group.date_reset,
        )

    last_qs = last_qs.order_by("-date_creation")

    # ======================================================
    # Sous-requête : prêt actif
    # ======================================================

    pret_actif_subquery = PretDemande.objects.filter(
        member=OuterRef("pk"),
        statut="APPROVED",
    )

    # ======================================================
    # Agrégation des membres
    # ======================================================

    sum_filter = Q(
        versements_ec__statut__in=["VALIDE", "EN_ATTENTE"]
    )

    if group.date_reset:
        sum_filter &= Q(
            versements_ec__date_creation__gte=group.date_reset
        )

    membres = (
        GroupMember.objects
        .filter(
            group=group,
            actif=True,
        )
        .select_related("user")
        .annotate(
            total_montant=Coalesce(
                Sum(
                    "versements_ec__montant",
                    filter=sum_filter,
                ),
                Value(
                    0,
                    output_field=DecimalField(
                        max_digits=12,
                        decimal_places=0,
                    ),
                ),
            ),
            last_amount=Subquery(
                last_qs.values("montant")[:1]
            ),
            last_date=Subquery(
                last_qs.values("date_creation")[:1]
            ),
            a_pret_actif=Exists(
                pret_actif_subquery
            ),
        )
        .order_by("id")
    )

    # ======================================================
    # Totaux financiers de base
    # ======================================================

    total_montant = Decimal(
        str(group.total_versements_valides or 0)
    )

    total_prets = Decimal(
        str(group.total_prets_approuves or 0)
    )

    caisse_disponible = Decimal(
        str(group.caisse_disponible or 0)
    )

    # ======================================================
    # Prêts approuvés du groupe
    # ======================================================

    prets_approuves = (
        PretDemande.objects
        .filter(
            member__group=group,
            statut="APPROVED",
        )
        .select_related(
            "member",
            "member__user",
        )
    )

    total_interets = Decimal("0")
    total_penalites = Decimal("0")

    for pret in prets_approuves:
        montant_pret = Decimal(
            str(pret.montant or 0)
        )

        taux_interet = Decimal(
            str(pret.interet or 0)
        )

        montant_interet = (
            montant_pret
            * taux_interet
            / Decimal("100")
        )

        total_interets += montant_interet

        # Les pénalités seront ajoutées ici lorsqu'un retard réel
        # sera constaté et calculé depuis les remboursements.
        total_penalites += Decimal("0")

    total_interets = total_interets.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    total_penalites = total_penalites.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    total_general = (
        total_montant
        + total_interets
        + total_penalites
    )

    # ======================================================
    # Journaux d'actions
    # ======================================================

    actions = (
        ActionLog.objects
        .filter(group=group)
        .select_related("user")
        .order_by("-date")[:10]
    )

    # ======================================================
    # Demandes de prêt en attente
    # ======================================================

    pending_prets = (
        PretDemande.objects
        .filter(
            member__group=group,
            statut="PENDING",
        )
        .select_related(
            "member",
            "member__user",
        )
        .order_by("-created_at")
    )

    # ======================================================
    # Versements en attente
    # ======================================================

    versements_en_attente = (
        Versement.objects
        .filter(
            member__group=group,
            statut="EN_ATTENTE",
        )
        .select_related(
            "member",
            "member__user",
        )
        .order_by("-date_creation")
    )

    # ======================================================
    # Lien d'invitation
    # ======================================================

    code = str(
        group.code_invitation or group.uuid
    )

    invite_url = request.build_absolute_uri(
        reverse(
            "accounts:inscription_et_rejoindre",
            args=[code],
        )
    )

    # ======================================================
    # Vérification administrateur
    # ======================================================

    user_is_admin = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    # ======================================================
    # Contexte
    # ======================================================

    context = {
        "group": group,
        "membres": membres,
        "total_montant": total_montant,
        "total_prets": total_prets,
        "caisse_disponible": caisse_disponible,
        "total_interets": total_interets,
        "total_penalites": total_penalites,
        "total_general": total_general,
        "admin_user": group.admin,
        "actions": actions,
        "user_is_admin": user_is_admin,
        "invite_url": invite_url,
        "remb_group": remb_group,
        "pending_prets": pending_prets,
        "versements_en_attente": versements_en_attente,
        "notifications": notifications,
    }

    return render(
        request,
        "epargnecredit/group_detail.html",
        context,
    )


# ==========================================================
# Création d'un groupe
# ==========================================================

@login_required
@transaction.atomic
def ajouter_groupe_view(request):
    """
    Crée un groupe d'épargne et son groupe de remboursement.

    L'utilisateur connecté devient administrateur et membre
    du groupe principal.
    """

    if request.method == "POST":
        form = GroupForm(request.POST)

        if form.is_valid():
            try:
                # Groupe principal
                group = form.save(commit=False)
                group.admin = request.user
                group.is_remboursement = False
                group.parent_group = None
                group.save()

                # L'administrateur devient membre du groupe principal
                GroupMember.objects.get_or_create(
                    group=group,
                    user=request.user,
                    defaults={
                        "montant": 0,
                        "actif": True,
                    },
                )

                # Groupe de remboursement associé
                group_remb = Group.objects.create(
                    nom=f"{group.nom} — Remboursement",
                    admin=request.user,
                    is_remboursement=True,
                    parent_group=group,
                    montant_base=0,
                )

                # Lien d'invitation du groupe principal
                lien_invitation = request.build_absolute_uri(
                    reverse(
                        "accounts:inscription_et_rejoindre",
                        args=[str(group.code_invitation)],
                    )
                )

                # Envoi simulé de l'invitation
                envoyer_invitation(
                    request.user.phone,
                    lien_invitation,
                )

                lien_remb = reverse(
                    "epargnecredit:group_detail_remboursement",
                    args=[group_remb.id],
                )

                messages.success(
                    request,
                    (
                        f"Groupe « {group.nom} » créé avec succès. "
                        "Vous avez été ajouté comme membre. "
                        "Le groupe de remboursement a également été créé : "
                        f"<a href='{lien_remb}'>voir le groupe de remboursement</a>."
                    ),
                )

                return redirect(
                    "epargnecredit:dashboard_epargne_credit"
                )

            except IntegrityError as exc:
                messages.error(
                    request,
                    f"Conflit lors de la création du groupe : {exc}",
                )

            except Exception as exc:
                messages.error(
                    request,
                    f"Erreur lors de la création du groupe : {exc}",
                )

    else:
        form = GroupForm()

    return render(
        request,
        "epargnecredit/ajouter_groupe.html",
        {
            "form": form,
            "title": "Créer un groupe",
        },
    )


# ==========================================================
# Réinitialisation du cycle
# ==========================================================

@login_required
@transaction.atomic
def reset_cycle_view(
    request: HttpRequest,
    group_id: int,
) -> HttpResponse:
    """
    Réinitialise un cycle d'épargne/crédit.

    GET :
        affiche la page de confirmation.

    POST :
        - remet les montants des membres à zéro ;
        - supprime les écritures ÉpargneCrédit si le modèle existe ;
        - supprime les versements du groupe ;
        - enregistre la date de réinitialisation.
    """

    group = get_object_or_404(
        Group,
        id=group_id,
    )

    user = request.user

    is_group_admin = (
        user == getattr(group, "admin", None)
    )

    is_super_admin = (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_super_admin", False)
    )

    if not (is_group_admin or is_super_admin):
        messages.error(
            request,
            "Vous n'avez pas la permission de réinitialiser ce groupe.",
        )
        return redirect(
            "epargnecredit:dashboard_epargne_credit"
        )

    if request.method != "POST":
        membres = (
            GroupMember.objects
            .filter(group=group)
            .select_related("user")
        )

        return render(
            request,
            "epargnecredit/confirm_reset_cycle.html",
            {
                "group": group,
                "members": membres,
                "date_reset_precedent": group.date_reset,
            },
        )

    membres = GroupMember.objects.filter(
        group=group
    )

    # Remise à zéro du montant des membres
    for membre in membres:
        if hasattr(membre, "montant"):
            membre.montant = 0
            membre.save(update_fields=["montant"])

    # Suppression des écritures EpargneCredit si le modèle existe
    try:
        EpargneCredit = apps.get_model(
            "epargnecredit",
            "EpargneCredit",
        )
    except LookupError:
        EpargneCredit = None

    if EpargneCredit is not None:
        EpargneCredit.objects.filter(
            member__group=group
        ).delete()

    # Suppression des versements du cycle
    Versement.objects.filter(
        member__group=group
    ).delete()

    # Date de réinitialisation
    group.date_reset = timezone.now()
    group.save(update_fields=["date_reset"])

    messages.success(
        request,
        (
            f"✅ Le cycle du groupe « {group.nom} » "
            "a été réinitialisé avec succès."
        ),
    )

    return redirect(
        "epargnecredit:group_detail",
        group_id=group.id,
    )
