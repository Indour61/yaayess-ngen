import random

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from ..forms import CustomUserCreationForm
from ..models import CustomUser


# ==========================================================
# INSCRIPTION
# ==========================================================

def signup_view(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)

        phone = (request.POST.get("phone") or "").strip()

        # --------------------------------------------------
        # NUMERO DE TELEPHONE DEJA UTILISE
        # --------------------------------------------------
        if phone and CustomUser.objects.filter(phone=phone).exists():
            messages.error(
                request,
                "Ce numéro de téléphone existe déjà. "
                "Veuillez vous connecter ou utiliser un autre numéro.",
            )

            return render(
                request,
                "accounts/signup.html",
                {"form": form},
            )

        # --------------------------------------------------
        # CREATION DU COMPTE
        # --------------------------------------------------
        if form.is_valid():
            user = form.save(commit=False)

            # Le compte sera activé après validation OTP
            user.is_active = False
            user.save()

            # Génération OTP à 6 chiffres
            otp = str(random.randint(100000, 999999))

            request.session["otp"] = otp
            request.session["phone"] = user.phone
            request.session["otp_time"] = timezone.now().isoformat()

            # Développement uniquement.
            # Ne pas conserver l'OTP dans les logs en production.
            print(f"[OTP NEW USER] {otp} -> {user.phone}")

            messages.success(
                request,
                "Un code de vérification a été envoyé.",
            )

            return redirect("accounts:verify_otp")

        # Formulaire invalide
        print("FORM ERRORS:", form.errors)

        messages.error(
            request,
            "Veuillez corriger les erreurs du formulaire.",
        )

    else:
        form = CustomUserCreationForm()

    return render(
        request,
        "accounts/signup.html",
        {"form": form},
    )


# ==========================================================
# CONNEXION
# ==========================================================

def login_view(request):
    # Utilisateur déjà connecté
    if request.user.is_authenticated:
        return redirect_user(request.user)

    if request.method == "POST":
        phone = (request.POST.get("phone") or "").strip()
        password = request.POST.get("password") or ""

        if not phone or not password:
            messages.error(
                request,
                "Veuillez saisir votre téléphone et votre mot de passe.",
            )

            return render(
                request,
                "accounts/login.html",
            )

        # PhoneBackend permet l'authentification par téléphone
        user = authenticate(
            request,
            username=phone,
            password=password,
        )

        if user is not None:
            if not user.is_active:
                messages.error(
                    request,
                    "Votre compte est désactivé.",
                )

                return render(
                    request,
                    "accounts/login.html",
                )

            login(request, user)

            display_name = (
                getattr(user, "nom", None)
                or getattr(user, "phone", "")
            )

            messages.success(
                request,
                f"Connexion réussie. Bienvenue {display_name} !",
            )

            next_url = (
                request.POST.get("next")
                or request.GET.get("next")
            )

            if (
                next_url
                and next_url != "/accounts/login/"
            ):
                return redirect(next_url)

            return redirect_user(user)

        messages.error(
            request,
            "Téléphone ou mot de passe incorrect.",
        )

    return render(
        request,
        "accounts/login.html",
    )


# ==========================================================
# DECONNEXION
# ==========================================================

@login_required
def logout_view(request):
    logout(request)

    messages.success(
        request,
        "Vous avez été déconnecté.",
    )

    return redirect("accounts:login")


# ==========================================================
# REDIRECTION SELON LE MODULE
# ==========================================================

def redirect_user(user):
    """
    Oriente l'utilisateur vers son module principal
    selon la valeur du champ `option`.
    """

    option = getattr(user, "option", None)

    # Tontine
    if option == "1":
        return redirect(
            "cotisationtontine:dashboard_tontine_simple"
        )

    # Epargne & Crédit
    if option == "2":
        return redirect(
            "epargnecredit:dashboard_epargne_credit"
        )

    return redirect("accounts:landing")


# ==========================================================
# HOME REDIRECT
# ==========================================================

@login_required
def home_redirect(request):
    """
    Redirige un utilisateur connecté vers son module.
    """

    return redirect_user(request.user)


# ==========================================================
# LANDING PAGE
# ==========================================================

def landing_view(request):
    """
    Page d'accueil.

    - Utilisateur non connecté :
      affiche la landing page.

    - Utilisateur connecté :
      redirige vers son module.
    """

    if request.user.is_authenticated:
        return redirect_user(request.user)

    return render(
        request,
        "landing.html",
    )