from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from epargnecredit.forms import PretDemandeForm
from epargnecredit.models import (
    Group,
    GroupMember,
    PretDemande,
    Versement,
)


# ==========================================================
# Création d'une demande de prêt
# ==========================================================

@login_required
@transaction.atomic
def demande_pret(request, member_id: int):
    """
    Crée une demande de prêt pour un membre.

    La demande peut être créée par :
    - le membre concerné ;
    - l'administrateur du groupe ;
    - un super-administrateur ;
    - un superutilisateur.

    Un membre ne peut pas avoir simultanément :
    - plusieurs demandes en attente ;
    - plusieurs prêts actifs.
    """

    member = get_object_or_404(
        GroupMember.objects.select_related(
            "user",
            "group",
            "group__admin",
        ),
        id=member_id,
        actif=True,
    )

    group = member.group

    # ======================================================
    # Vérification des permissions
    # ======================================================

    has_permission = (
        request.user == member.user
        or request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_permission:
        messages.error(
            request,
            (
                "Vous n'avez pas les droits nécessaires "
                "pour créer une demande de prêt."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Traitement POST
    # ======================================================

    if request.method == "POST":
        form = PretDemandeForm(request.POST)

        if form.is_valid():
            # Vérifier une demande déjà en attente
            demande_en_attente = PretDemande.objects.filter(
                member=member,
                statut="PENDING",
            ).exists()

            if demande_en_attente:
                messages.warning(
                    request,
                    (
                        "⚠️ Une demande de prêt est déjà "
                        "en attente pour ce membre."
                    ),
                )
                return redirect(
                    "epargnecredit:group_detail",
                    group_id=group.id,
                )

            # Vérifier un prêt actif
            pret_actif = PretDemande.objects.filter(
                member=member,
                statut="APPROVED",
            ).exists()

            if pret_actif:
                messages.error(
                    request,
                    (
                        "❌ Ce membre possède déjà un prêt actif. "
                        "Le prêt doit être soldé avant une nouvelle demande."
                    ),
                )
                return redirect(
                    "epargnecredit:group_detail",
                    group_id=group.id,
                )

            try:
                demande = form.save(commit=False)
                demande.member = member
                demande.statut = "PENDING"
                demande.save()

                messages.success(
                    request,
                    (
                        f"✅ La demande de prêt de "
                        f"{demande.montant:,.0f} FCFA "
                        "a été enregistrée avec succès."
                    ),
                )

                return redirect(
                    "epargnecredit:group_detail",
                    group_id=group.id,
                )

            except IntegrityError:
                messages.warning(
                    request,
                    (
                        "⚠️ Une demande de prêt est déjà "
                        "en attente pour ce membre."
                    ),
                )

                return redirect(
                    "epargnecredit:group_detail",
                    group_id=group.id,
                )

        messages.error(
            request,
            "Veuillez corriger les erreurs du formulaire.",
        )

        return render(
            request,
            "epargnecredit/demande_pret_form.html",
            {
                "form": form,
                "member": member,
                "group": group,
            },
            status=400,
        )

    # ======================================================
    # Affichage GET
    # ======================================================

    form = PretDemandeForm()

    return render(
        request,
        "epargnecredit/demande_pret_form.html",
        {
            "form": form,
            "member": member,
            "group": group,
        },
    )


# ==========================================================
# Validation d'une demande de prêt
# ==========================================================

@login_required
@require_http_methods(["POST"])
@transaction.atomic
def pret_valider(request, pk: int):
    """
    Valide une demande de prêt en attente.

    Seul l'administrateur du groupe, un super-administrateur
    ou un superutilisateur peut valider la demande.
    """

    demande = get_object_or_404(
        PretDemande.objects
        .select_for_update()
        .select_related(
            "member",
            "member__group",
            "member__group__admin",
            "member__user",
        ),
        pk=pk,
    )

    group = demande.member.group

    # ======================================================
    # Vérification des permissions
    # ======================================================

    has_permission = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_permission:
        messages.error(
            request,
            "Seul l'administrateur du groupe peut valider ce prêt.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Vérification du statut
    # ======================================================

    if demande.statut != "PENDING":
        messages.info(
            request,
            "Cette demande a déjà été traitée.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Vérification d'un autre prêt actif
    # ======================================================

    autre_pret_actif = (
        PretDemande.objects
        .filter(
            member=demande.member,
            statut="APPROVED",
        )
        .exclude(pk=demande.pk)
        .exists()
    )

    if autre_pret_actif:
        messages.error(
            request,
            "Ce membre possède déjà un autre prêt actif.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Vérification de la caisse disponible
    # ======================================================

    total_versements_valides = (
        Versement.objects
        .filter(
            member__group=group,
            statut="VALIDE",
        )
        .aggregate(total=Sum("montant"))
        .get("total")
        or 0
    )

    total_prets_approuves = (
        PretDemande.objects
        .filter(
            member__group=group,
            statut="APPROVED",
        )
        .aggregate(total=Sum("montant"))
        .get("total")
        or 0
    )

    caisse_disponible = (
        total_versements_valides
        - total_prets_approuves
    )

    if caisse_disponible < demande.montant:
        messages.error(
            request,
            (
                "❌ Caisse insuffisante pour valider ce prêt. "
                f"Disponible : {caisse_disponible:,.0f} FCFA ; "
                f"demande : {demande.montant:,.0f} FCFA."
            ),
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Validation de la demande
    # ======================================================

    demande.statut = "APPROVED"
    demande.decided_by = request.user
    demande.decided_at = timezone.now()
    demande.commentaire = (
        request.POST.get("commentaire", "")
        or ""
    ).strip()

    demande.save(
        update_fields=[
            "statut",
            "decided_by",
            "decided_at",
            "commentaire",
        ]
    )

    # ======================================================
    # Groupe de remboursement
    # ======================================================

    remboursement_group = None

    if hasattr(group, "get_remboursement_group"):
        remboursement_group = (
            group.get_remboursement_group()
        )

    if remboursement_group is None:
        remboursement_group = Group.objects.create(
            nom=f"{group.nom} — Remboursement",
            admin=group.admin,
            is_remboursement=True,
            parent_group=group,
            montant_base=0,
        )

    # Ajouter le bénéficiaire dans le groupe de remboursement
    GroupMember.objects.get_or_create(
        group=remboursement_group,
        user=demande.member.user,
        defaults={
            "montant": 0,
            "actif": True,
        },
    )

    messages.success(
        request,
        (
            f"✅ Le prêt de {demande.montant:,.0f} FCFA "
            f"accordé à {demande.member.user} a été approuvé."
        ),
    )

    return redirect(
        "epargnecredit:group_detail_remboursement",
        group_id=remboursement_group.id,
    )


# ==========================================================
# Refus d'une demande de prêt
# ==========================================================

@login_required
@require_http_methods(["POST"])
@transaction.atomic
def pret_refuser(request, pk: int):
    """
    Refuse une demande de prêt en attente.

    Seul l'administrateur du groupe, un super-administrateur
    ou un superutilisateur peut refuser la demande.
    """

    demande = get_object_or_404(
        PretDemande.objects
        .select_for_update()
        .select_related(
            "member",
            "member__group",
            "member__group__admin",
            "member__user",
        ),
        pk=pk,
    )

    group = demande.member.group

    # ======================================================
    # Vérification des permissions
    # ======================================================

    has_permission = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not has_permission:
        messages.error(
            request,
            "Seul l'administrateur du groupe peut refuser ce prêt.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Vérification du statut
    # ======================================================

    if demande.statut != "PENDING":
        messages.info(
            request,
            "Cette demande a déjà été traitée.",
        )
        return redirect(
            "epargnecredit:group_detail",
            group_id=group.id,
        )

    # ======================================================
    # Refus de la demande
    # ======================================================

    demande.statut = "REJECTED"
    demande.decided_by = request.user
    demande.decided_at = timezone.now()
    demande.commentaire = (
        request.POST.get("commentaire", "")
        or ""
    ).strip()

    demande.save(
        update_fields=[
            "statut",
            "decided_by",
            "decided_at",
            "commentaire",
        ]
    )

    messages.success(
        request,
        (
            f"La demande de prêt de "
            f"{demande.montant:,.0f} FCFA "
            f"de {demande.member.user} a été refusée."
        ),
    )

    return redirect(
        "epargnecredit:group_detail",
        group_id=group.id,
    )
