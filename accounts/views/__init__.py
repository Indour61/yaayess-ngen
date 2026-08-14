# ==========================================================
# API
# ==========================================================

from .api import (
    LoginAPIView,
    MeView,
    RegisterAPIView,
)


# ==========================================================
# AUTHENTIFICATION
# ==========================================================

from .auth import (
    home_redirect,
    landing_view,
    login_view,
    logout_view,
    redirect_user,
    signup_view,
)


# ==========================================================
# DASHBOARDS
# ==========================================================

from .dashboards import (
    attente_validation,
    create_group,
    dashboard,
    dashboard_admin,
    dashboard_epargne_credit,
    dashboard_membre,
)


# ==========================================================
# INVITATIONS
# ==========================================================

from .invitations import (
    inscription_et_rejoindre,
)


# ==========================================================
# FACTURES
# ==========================================================

from .invoices import (
    invoice_pdf,
    invoices_dashboard,
)


# ==========================================================
# OTP
# ==========================================================

from .otp import (
    resend_otp_view,
    verify_otp_view,
)


# ==========================================================
# PROFIL
# ==========================================================

from .profile import (
    profile_view,
)


# ==========================================================
# EXPORTS PUBLICS
# ==========================================================

__all__ = [
    # Auth
    "signup_view",
    "login_view",
    "logout_view",
    "landing_view",
    "home_redirect",
    "redirect_user",

    # OTP
    "verify_otp_view",
    "resend_otp_view",

    # Profile
    "profile_view",

    # Invitations
    "inscription_et_rejoindre",

    # Dashboards
    "dashboard",
    "dashboard_admin",
    "dashboard_membre",
    "dashboard_epargne_credit",
    "attente_validation",
    "create_group",

    # Invoices
    "invoices_dashboard",
    "invoice_pdf",

    # API
    "RegisterAPIView",
    "LoginAPIView",
    "MeView",
]