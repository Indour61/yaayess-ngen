from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import CustomUser
from epargnecredit.forms import GroupMemberForm
from epargnecredit.models import Group, GroupMember


@login_required
def ajouter_membre_view(request, group_id):
    """
    Ajoute un membre à un groupe existant.

    Seul l'administrateur du groupe, un super administrateur
    ou un superutilisateur peut ajouter un membre.
    """

    group = get_object_or_404(
        Group.objects.select_related("admin"),
        id=group_id,
    )

    # ======================================================
    # Vérification des permissions
    # ======================================================

    user_is_admin = (
        request.user == group.admin
        or getattr(request.user, "is_super_admin", False)
        or getattr(request.user, "is_superuser", False)
    )

    if not user_is_admin:
        messages.error(
            request,
            (
                "⚠️ Vous n'avez pas les droits nécessaires "
                "pour ajouter un membre à ce groupe."
            ),
        )
        return redirect(
            "epargnecredit:dashboard_epargne_credit"
        )

    # ======================================================
    # Traitement du formulaire
    # ======================================================

    if request.method == "POST":
        form = GroupMemberForm(request.POST)

        if form.is_valid():
            phone = form.cleaned_data["phone"]
            nom = (form.cleaned_data.get("nom") or "").strip()

            # ==================================================
            # Création ou récupération de l'utilisateur
            # ==================================================

            defaults = {
                "nom": nom or f"Utilisateur {phone}",
            }

            user, created_user = CustomUser.objects.get_or_create(
                phone=phone,
                defaults=defaults,
            )

            # Si l'utilisateur existe déjà, conserver son nom actuel
            if not created_user:
                nom_existant = getattr(user, "nom", "") or ""

                if nom and nom_existant and nom_existant != nom:
                    messages.warning(
                        request,
                        (
                            f"⚠️ Ce numéro est déjà associé à "
                            f"« {nom_existant} ». "
                            f"Le nom saisi « {nom} » a été ignoré."
                        ),
                    )

                nom = nom_existant or nom

            # ==================================================
            # Vérification d'un doublon dans le groupe
            # ==================================================

            membre_existant = (
                GroupMember.objects
                .filter(
                    group=group,
                    user=user,
                )
                .first()
            )

            if membre_existant:
                if not getattr(membre_existant, "actif", True):
                    membre_existant.actif = True
                    membre_existant.save(update_fields=["actif"])

                    messages.success(
                        request,
                        (
                            f"✅ {user.nom or user.phone} a été "
                            f"réactivé dans le groupe « {group.nom} »."
                        ),
                    )
                else:
                    messages.info(
                        request,
                        (
                            f"ℹ️ {user.nom or user.phone} est déjà "
                            f"membre du groupe « {group.nom} »."
                        ),
                    )

                return redirect(
                    "epargnecredit:group_detail",
                    group_id=group.id,
                )

            # ==================================================
            # Détection d'un nom déjà utilisé dans le groupe
            # ==================================================

            alias = None

            if nom:
                nom_deja_utilise = (
                    GroupMember.objects
                    .filter(
                        group=group,
                        user__nom__iexact=nom,
                    )
                    .exclude(
                        user__phone=phone,
                    )
                    .exists()
                )

                if nom_deja_utilise:
                    alias = f"{nom} ({phone})"

                    messages.warning(
                        request,
                        (
                            f"⚠️ Le nom « {nom} » existe déjà dans "
                            "ce groupe avec un autre numéro. "
                            f"L'alias « {alias} » sera utilisé."
                        ),
                    )

            # ==================================================
            # Création du membre
            # ==================================================

            membre = GroupMember.objects.create(
                group=group,
                user=user,
                montant=0,
                alias=alias,
                actif=True,
            )

            nom_affiche = (
                membre.alias
                or getattr(user, "nom", None)
                or getattr(user, "phone", None)
                or str(user)
            )

            messages.success(
                request,
                (
                    f"✅ {nom_affiche} a été ajouté au groupe "
                    f"« {group.nom} »."
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

    else:
        form = GroupMemberForm()

    # ======================================================
    # Affichage du formulaire
    # ======================================================

    return render(
        request,
        "epargnecredit/ajouter_membre.html",
        {
            "group": group,
            "form": form,
        },
    )
