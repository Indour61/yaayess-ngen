from django.urls import path

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from accounts.jwt_serializer import PhoneTokenObtainPairSerializer

from .views import (
    LoginAPIView,
    MeView,
    RegisterAPIView,
    attente_validation,
    create_group,
    inscription_et_rejoindre,
    invoice_pdf,
    invoices_dashboard,
    landing_view,
    login_view,
    logout_view,
    resend_otp_view,
    signup_view,
    verify_otp_view,
)
from .views_admin import saas_dashboard, toggle_group_access
from .views_compta import compta_dashboard
from .views_recus import mes_recus


class PhoneTokenObtainPairView(TokenObtainPairView):
    serializer_class = PhoneTokenObtainPairSerializer


app_name = "accounts"


urlpatterns = [
    # Landing
    path("", landing_view, name="landing"),

    # Authentication
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("signup/", signup_view, name="signup"),

    # OTP
    path("verify-otp/", verify_otp_view, name="verify_otp"),
    path("resend-otp/", resend_otp_view, name="resend_otp"),

    # Invitations / groups
    path(
        "rejoindre/<str:code>/",
        inscription_et_rejoindre,
        name="inscription_et_rejoindre",
    ),
    path(
        "attente-validation/",
        attente_validation,
        name="attente_validation",
    ),
    path(
        "create-group/",
        create_group,
        name="create_group",
    ),

    # User API
    path(
        "me/",
        MeView.as_view(),
        name="api_me",
    ),

    # Authentication API
    path(
        "api/register/",
        RegisterAPIView.as_view(),
        name="api_register",
    ),
    path(
        "api/login/",
        LoginAPIView.as_view(),
        name="api_login",
    ),

    # JWT
    path(
        "api/token/",
        PhoneTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path(
        "api/token/refresh/",
        TokenRefreshView.as_view(),
        name="token_refresh",
    ),

    # SaaS admin
    path(
        "super-admin/dashboard/",
        saas_dashboard,
        name="saas_dashboard",
    ),
    path(
        "super-admin/toggle-group/<str:type>/<int:group_id>/",
        toggle_group_access,
        name="toggle_group_access",
    ),

    path(
        "saas-dashboard/",
        saas_dashboard,
        name="saas_dashboard_alt",
    ),
    path(
        "toggle-group/<int:group_id>/",
        toggle_group_access,
        name="toggle_group_access_alt",
    ),

    # Accounting
    path(
        "compta-dashboard/",
        compta_dashboard,
        name="compta_dashboard",
    ),

    # Receipts
    path(
        "mes-recus/",
        mes_recus,
        name="mes_recus",
    ),

    # Invoices
    path(
        "factures/",
        invoices_dashboard,
        name="invoices_dashboard",
    ),
    path(
        "invoice/<int:invoice_id>/pdf/",
        invoice_pdf,
        name="invoice_pdf",
    ),
]