import random
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render
from django.utils import timezone

from ..models import CustomUser


# =========================================================
# VERIFY OTP
# =========================================================

def verify_otp_view(request):
    phone = request.session.get("phone")
    otp_session = request.session.get("otp")
    otp_time_raw = request.session.get("otp_time")

    # Session OTP inexistante ou perdue
    if not phone or not otp_session or not otp_time_raw:
        messages.error(
            request,
            "Session expirée. Veuillez vous réinscrire.",
        )
        return redirect("accounts:signup")

    # Conversion de la date OTP
    try:
        otp_time = timezone.datetime.fromisoformat(
            otp_time_raw
        )

        if timezone.is_naive(otp_time):
            otp_time = timezone.make_aware(
                otp_time
            )

    except (TypeError, ValueError):
        messages.error(
            request,
            "Session OTP invalide. Veuillez recommencer.",
        )
        return redirect("accounts:signup")

    # Expiration OTP : 2 minutes
    if timezone.now() > otp_time + timedelta(minutes=2):
        messages.error(
            request,
            "Code expiré. Demandez un nouveau code.",
        )
        return redirect("accounts:resend_otp")

    # Vérification du code
    if request.method == "POST":
        otp_user = (
            request.POST.get("otp")
            or ""
        ).strip()

        if otp_user != str(otp_session):
            messages.error(
                request,
                "Code incorrect.",
            )
            return render(
                request,
                "accounts/verify_otp.html",
            )

        try:
            user = CustomUser.objects.get(
                phone=phone
            )
        except CustomUser.DoesNotExist:
            messages.error(
                request,
                "Utilisateur introuvable.",
            )
            return redirect("accounts:signup")

        # Activation du compte
        if not user.is_active:
            user.is_active = True
            user.save(
                update_fields=["is_active"]
            )

        # Connexion après validation OTP
        login(
            request,
            user,
            backend="accounts.auth_backend.PhoneBackend",
        )

        # Nettoyage de la session OTP
        for key in (
            "otp",
            "phone",
            "otp_time",
        ):
            request.session.pop(
                key,
                None,
            )

        messages.success(
            request,
            "Compte activé avec succès !",
        )

        return redirect(
            "accounts:landing"
        )

    return render(
        request,
        "accounts/verify_otp.html",
    )


# =========================================================
# RESEND OTP
# =========================================================

def resend_otp_view(request):
    phone = request.session.get("phone")
    last_otp_time_raw = request.session.get(
        "otp_time"
    )

    if not phone:
        messages.error(
            request,
            "Session expirée. Veuillez vous réinscrire.",
        )
        return redirect("accounts:signup")

    # Anti-spam : délai minimum de 30 secondes
    if last_otp_time_raw:
        try:
            last_otp_time = (
                timezone.datetime.fromisoformat(
                    last_otp_time_raw
                )
            )

            if timezone.is_naive(
                last_otp_time
            ):
                last_otp_time = (
                    timezone.make_aware(
                        last_otp_time
                    )
                )

            next_allowed_time = (
                last_otp_time
                + timedelta(seconds=30)
            )

            if timezone.now() < next_allowed_time:
                messages.warning(
                    request,
                    (
                        "Veuillez patienter avant "
                        "de demander un nouveau code."
                    ),
                )

                return redirect(
                    "accounts:verify_otp"
                )

        except (TypeError, ValueError):
            # Une valeur de session invalide ne doit
            # pas bloquer définitivement le renvoi.
            pass

    # Nouveau code OTP
    otp = str(
        random.randint(
            100000,
            999999,
        )
    )

    request.session["otp"] = otp
    request.session[
        "otp_time"
    ] = timezone.now().isoformat()

    request.session.modified = True

    # À remplacer par l'envoi SMS réel.
    # Éviter d'afficher l'OTP dans les logs en production.
    print(
        f"[RESEND OTP] {otp} -> {phone}"
    )

    messages.success(
        request,
        "Nouveau code envoyé.",
    )

    return redirect(
        "accounts:verify_otp"
    )