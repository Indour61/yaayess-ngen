from django.contrib.auth import get_user_model
from django.db import transaction

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from ..serializers import UserSerializer


User = get_user_model()


# ==========================================================
# LOGIN API
# ==========================================================

class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        password = request.data.get("password") or ""

        if not phone or not password:
            return Response(
                {
                    "error": (
                        "Téléphone et mot de passe requis"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur introuvable"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": "Compte désactivé"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.check_password(password):
            return Response(
                {"error": "Mot de passe incorrect"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "status": "success",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "phone": user.phone,
                    "nom": getattr(user, "nom", ""),
                    "option": getattr(user, "option", None),
                    "is_validated": getattr(
                        user,
                        "is_validated",
                        False,
                    ),
                    "is_staff": user.is_staff,
                },
            },
            status=status.HTTP_200_OK,
        )


# ==========================================================
# REGISTER API
# ==========================================================

class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        password = request.data.get("password") or ""
        nom = (request.data.get("nom") or "").strip()
        option = request.data.get("option")

        if not all(
            [
                phone,
                password,
                nom,
                option,
            ]
        ):
            return Response(
                {
                    "error": (
                        "Tous les champs sont obligatoires"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(phone=phone).exists():
            return Response(
                {"error": "Téléphone déjà utilisé"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_user(
            phone=phone,
            password=password,
            nom=nom,
            option=option,
        )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Compte créé avec succès",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "phone": user.phone,
                    "nom": getattr(user, "nom", ""),
                    "option": getattr(
                        user,
                        "option",
                        None,
                    ),
                },
            },
            status=status.HTTP_201_CREATED,
        )


# ==========================================================
# CURRENT USER API
# ==========================================================

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(
            request.user
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )