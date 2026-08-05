from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import CustomUser
from cotisationtontine.forms import GroupMemberForm
from cotisationtontine.models import Group, GroupMember


@login_required
@transaction.atomic
def ajouter_membre_view(request, group_id):

    group = get_object_or_404(Group, id=group_id)

    # ðŸ”’ 1. SÃ©curitÃ© admin
    if group.admin != request.user:
        messages.error(request, "âš ï¸ Vous n'avez pas les droits pour ajouter un membre Ã  ce groupe.")
        return redirect("cotisationtontine:dashboard_tontine_simple")

    # ðŸ”’ 2. BLOQUAGE MÃ‰TIER (TRÃˆS IMPORTANT)
    if group.tirage_effectue:
        messages.error(request, "ðŸš« Impossible d'ajouter un membre : le cycle est dÃ©jÃ  en cours.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    if group.cycle_termine:
        messages.error(request, "ðŸš« Cycle terminÃ©. Veuillez rÃ©initialiser avant d'ajouter un membre.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    if request.method == "POST":
        form = GroupMemberForm(request.POST)

        if form.is_valid():
            phone = form.cleaned_data.get("phone")
            nom = form.cleaned_data.get("nom")

            # ðŸ”’ 3. VALIDATION NUMÃ‰RO
            if not phone:
                messages.error(request, "NumÃ©ro invalide.")
                return redirect(request.path)

            # ðŸ”’ 4. CrÃ©ation ou rÃ©cupÃ©ration utilisateur
            user, created_user = CustomUser.objects.get_or_create(
                phone=phone,
                defaults={"nom": nom or f"Utilisateur {phone}"}
            )

            # ðŸ”” Alerte si conflit nom
            if not created_user and user.nom != nom:
                messages.warning(
                    request,
                    f"âš ï¸ Ce numÃ©ro appartient dÃ©jÃ  Ã  {user.nom}. Nom fourni ignorÃ©."
                )
                nom = user.nom

            # ðŸ”’ 5. VÃ©rifier doublon dans groupe
            if GroupMember.objects.filter(group=group, user=user).exists():
                messages.info(request, f"â„¹ï¸ {user.nom} est dÃ©jÃ  membre du groupe.")
                return redirect("cotisationtontine:group_detail", group_id=group.id)

            # ðŸ”’ 6. DÃ©tection noms identiques
            existing = GroupMember.objects.filter(
                group=group,
                user__nom=nom
            ).exclude(user__phone=phone)

            alias = None
            if existing.exists():
                messages.warning(
                    request,
                    f"âš ï¸ Le nom '{nom}' existe dÃ©jÃ . Un alias sera utilisÃ©."
                )
                alias = f"{nom} ({phone})"

            # ðŸ”¥ 7. CRÃ‰ATION MEMBRE
            group_member = GroupMember.objects.create(
                group=group,
                user=user,
                montant=0,
                alias=alias
            )

            # ðŸ”” Message
            display_name = alias if alias else user.nom
            messages.success(request, f"âœ… {display_name} ajoutÃ© avec succÃ¨s.")

            return redirect("cotisationtontine:group_detail", group_id=group.id)

    else:
        form = GroupMemberForm()

    return render(request, "cotisationtontine/ajouter_membre.html", {
        "group": group,
        "form": form
    })

@login_required
def editer_membre_view(request, group_id, membre_id):
    group = get_object_or_404(Group, id=group_id)
    membre = get_object_or_404(GroupMember, id=membre_id, group=group)

    # ðŸ”’ SÃ©curitÃ©
    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "AccÃ¨s non autorisÃ©.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    if request.method == "POST":
        form = GroupMemberForm(request.POST, instance=membre)
        if form.is_valid():
            form.save()
            messages.success(request, "Membre modifiÃ© avec succÃ¨s âœ…")
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

    # ðŸ”’ 1. SÃ©curitÃ© admin
    if request.user != group.admin and not request.user.is_superuser:
        messages.error(request, "â›” AccÃ¨s non autorisÃ©.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # ðŸ”’ 2. BLOQUAGE SI CYCLE EN COURS
    if group.tirage_effectue:
        messages.error(request, "ðŸš« Impossible de supprimer un membre : le cycle est en cours.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # ðŸ”’ 3. BLOQUAGE SI CYCLE TERMINÃ‰
    if group.cycle_termine:
        messages.error(request, "ðŸš« Cycle terminÃ©. Veuillez rÃ©initialiser avant toute modification.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # ðŸ”’ 4. BLOQUAGE SI LE MEMBRE A DÃ‰JÃ€ REÃ‡U
    if membre.a_recu:
        messages.error(request, "ðŸš« Impossible : ce membre a dÃ©jÃ  reÃ§u la cagnotte.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # ðŸ”’ 5. BLOQUAGE SI LE MEMBRE A COTISÃ‰
    if membre.montant > 0:
        messages.error(request, "ðŸš« Impossible : ce membre a dÃ©jÃ  cotisÃ©.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # ðŸ”’ 6. PROTECTION MINIMUM (optionnel mais trÃ¨s important)
    total_membres = group.membres.filter(actif=True).count()
    if total_membres <= 1:
        messages.error(request, "ðŸš« Impossible de supprimer le dernier membre du groupe.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    # ðŸ”¥ 7. SUPPRESSION
    if request.method == "POST":
        membre.delete()
        messages.success(request, "âœ… Membre supprimÃ© avec succÃ¨s.")
        return redirect("cotisationtontine:group_detail", group_id=group.id)

    return render(request, "cotisationtontine/confirmer_suppression.html", {
        "membre": membre,
        "group": group
    })
