from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from ..decorators import admin_required, membre_required
from ..models import Notification

from cotisationtontine.models import Group


# ==========================================================
# HELPERS
# ==========================================================

def _notification_has_user_field():
    """
    Vérifie si le modèle Notification possède réellement
    un champ de base de données nommé 'user'.
    """
    return any(
        field.name == "user"
        for field in Notification._meta.get_fields()
    )


# ==========================================================
# DECORATORS
# ==========================================================

def validation_required(view_func):
    """
    Empêche l'accès au module Épargne & Crédit
    tant que le compte n'a pas été validé.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect("accounts:login")

        if (
            getattr(user, "option", None) == "2"
            and not getattr(user, "is_validated", False)
        ):
            messages.error(
                request,
                (
                    "Votre compte doit être validé par "
                    "l’administrateur avant d’accéder à "
                    "l’application Épargne & Crédit."
                ),
            )

            return redirect(
                "accounts:attente_validation"
            )

        return view_func(
            request,
            *args,
            **kwargs,
        )

    return wrapper


# ==========================================================
# DASHBOARD PRINCIPAL
# ==========================================================

@login_required
def dashboard(request):
    user = request.user

    # ------------------------------------------------------
    # NOTIFICATIONS
    # ------------------------------------------------------

    if _notification_has_user_field():
        notifications_queryset = (
            Notification.objects
            .filter(user=user)
            .order_by("-created_at")
        )

        unread_count = (
            Notification.objects
            .filter(
                user=user,
                is_read=False,
            )
            .count()
        )

        Notification.objects.filter(
            user=user,
            is_read=False,
        ).update(
            is_read=True
        )

    else:
        notifications_queryset = (
            Notification.objects
            .order_by("-created_at")
        )

        unread_count = (
            Notification.objects
            .filter(is_read=False)
            .count()
        )

        Notification.objects.filter(
            is_read=False
        ).update(
            is_read=True
        )

    notifications = notifications_queryset[:5]

    context = {
        "notifications": notifications,
        "unread_count": unread_count,
    }

    # ------------------------------------------------------
    # DASHBOARD SELON TYPE D'INSCRIPTION
    # ------------------------------------------------------

    choix = getattr(
        user,
        "choix_inscription",
        None,
    )

    if choix == "cotisationtontine":
        return render(
            request,
            "cotisationtontine/dashboard.html",
            context,
        )

    if choix == "epargnecredit":
        return render(
            request,
            "epargnecredit/dashboard.html",
            context,
        )

    return render(
        request,
        "dashboard.html",
        context,
    )


# ==========================================================
# DASHBOARD EPARGNE & CREDIT
# ==========================================================

@login_required
@validation_required
def dashboard_epargne_credit(request):
    return render(
        request,
        "epargnecredit/dashboard.html",
    )


# ==========================================================
# ATTENTE VALIDATION
# ==========================================================

@login_required
def attente_validation(request):
    """
    Page affichée lorsqu'un utilisateur Épargne & Crédit
    attend encore la validation de son compte.
    """

    user = request.user

    # Si le compte est déjà validé, inutile de rester ici.
    if getattr(user, "is_validated", False):
        return redirect(
            "epargnecredit:dashboard_epargne_credit"
        )

    return render(
        request,
        "accounts/attente_validation.html",
    )


# ==========================================================
# DASHBOARD ADMIN
# ==========================================================

@admin_required
def dashboard_admin(request):
    """
    Vue réservée aux administrateurs.
    """

    return render(
        request,
        "accounts/dashboard_admin.html",
    )


# ==========================================================
# DASHBOARD MEMBRE
# ==========================================================

@membre_required
def dashboard_membre(request):
    """
    Vue réservée aux membres.
    """

    return render(
        request,
        "accounts/dashboard_membre.html",
    )


# ==========================================================
# CREATION GROUPE
# ==========================================================

@login_required
def create_group(request):
    """
    Création d'un groupe de cotisation/tontine.
    """

    if request.method == "POST":
        nom = (
            request.POST.get("nom")
            or ""
        ).strip()

        if not nom:
            messages.error(
                request,
                "Le nom du groupe est obligatoire.",
            )

            return render(
                request,
                "accounts/create_group.html",
            )

        group = Group.objects.create(
            nom=nom,
            admin=request.user,
        )

        messages.success(
            request,
            (
                f"Le groupe « {group.nom} » "
                "a été créé avec succès."
            ),
        )

        return redirect(
            "cotisationtontine:group_detail",
            group.id,
        )

    return render(
        request,
        "accounts/create_group.html",
    )