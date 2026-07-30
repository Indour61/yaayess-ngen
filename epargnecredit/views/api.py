from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOptionTwo, IsSuperAdmin


class DashboardEpargneView(APIView):
    """
    Point d'entrée API du tableau de bord Épargne & Crédit.

    L'utilisateur doit :
    - être authentifié ;
    - disposer de l'option Épargne & Crédit.
    """

    permission_classes = [
        IsAuthenticated,
        IsOptionTwo,
    ]

    def get(self, request):
        """
        Retourne un message confirmant l'accès à l'espace
        Épargne & Crédit.
        """

        return Response(
            {
                "message": "Bienvenue Épargne & Crédit",
            }
        )


class AdminOnlyView(APIView):
    """
    Vue API de base réservée aux super-administrateurs.

    Cette classe peut être héritée par les vues API nécessitant
    les permissions ``IsAuthenticated`` et ``IsSuperAdmin``.
    """

    permission_classes = [
        IsAuthenticated,
        IsSuperAdmin,
    ]


class IsAdminOrSuper(BasePermission):
    """
    Autorise l'accès aux administrateurs Django et aux
    super-administrateurs YaayESS.
    """

    message = (
        "Vous devez être administrateur ou super-administrateur "
        "pour effectuer cette action."
    )

    def has_permission(self, request, view):
        """
        Vérifie que l'utilisateur est authentifié et possède
        au moins l'un des rôles administratifs requis.
        """

        user = request.user

        return bool(
            user
            and user.is_authenticated
            and (
                getattr(user, "is_staff", False)
                or getattr(user, "is_super_admin", False)
                or getattr(user, "is_superuser", False)
            )
        )
