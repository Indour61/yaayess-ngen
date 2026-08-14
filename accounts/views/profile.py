from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from ..models import CustomUser


@login_required
@transaction.atomic
def profile_view(request):
    """
    Affiche et permet de modifier le profil
    de l'utilisateur connecté.
    """

    user = request.user

    if request.method == "POST":
        nom = (request.POST.get("nom") or "").strip()
        email = (request.POST.get("email") or "").strip()
        phone = (request.POST.get("phone") or "").strip()

        updated_fields = []

        # ==================================================
        # NOM
        # ==================================================

        if nom and nom != user.nom:
            if (
                CustomUser.objects
                .filter(nom=nom)
                .exclude(pk=user.pk)
                .exists()
            ):
                messages.error(
                    request,
                    "Ce nom est déjà utilisé par un autre utilisateur.",
                )
            else:
                user.nom = nom
                updated_fields.append("nom")

        # ==================================================
        # EMAIL
        # ==================================================

        if email != (user.email or ""):
            if (
                email
                and CustomUser.objects
                .filter(email=email)
                .exclude(pk=user.pk)
                .exists()
            ):
                messages.error(
                    request,
                    "Cet email est déjà utilisé par un autre utilisateur.",
                )
            else:
                user.email = email
                updated_fields.append("email")

        # ==================================================
        # TELEPHONE
        # ==================================================

        if phone and phone != user.phone:
            if (
                CustomUser.objects
                .filter(phone=phone)
                .exclude(pk=user.pk)
                .exists()
            ):
                messages.error(
                    request,
                    "Ce numéro de téléphone est déjà utilisé "
                    "par un autre utilisateur.",
                )
            else:
                user.phone = phone
                updated_fields.append("phone")

        # ==================================================
        # SAUVEGARDE
        # ==================================================

        if updated_fields:
            user.save(
                update_fields=updated_fields
            )

            messages.success(
                request,
                "Votre profil a été mis à jour avec succès.",
            )
        else:
            messages.info(
                request,
                "Aucune modification détectée.",
            )

        return redirect(
            "accounts:profile"
        )

    return render(
        request,
        "accounts/profile.html",
        {
            "user": user,
        },
    )