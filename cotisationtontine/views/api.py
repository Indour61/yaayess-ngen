from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cotisationtontine.models import Group, GroupMember, Versement


class GroupDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, group_id):

        group = get_object_or_404(Group, id=group_id)

        # ðŸ”’ VÃ©rification accÃ¨s
        has_access = (
            group.admin_id == request.user.id
            or GroupMember.objects.filter(group=group, user=request.user).exists()
            or request.user.is_superuser
        )

        if not has_access:
            return Response({"error": "AccÃ¨s refusÃ©"}, status=403)

        membres = GroupMember.objects.filter(group=group).select_related("user")

        membres_data = []
        for membre in membres:
            total = (
                Versement.objects
                .filter(member=membre, statut="VALIDE")
                .aggregate(total=Sum("montant"))["total"] or 0
            )

            membres_data.append({
                "id": membre.id,
                "nom": membre.user.nom,
                "telephone": membre.user.phone,
                "total_verse": total
            })

        total_group = (
            Versement.objects
            .filter(member__group=group, statut="VALIDE")
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        return Response({
            "id": group.id,
            "nom": group.nom,
            "montant_base": group.montant,
            "total_cotise": total_group,
            "membres": membres_data,
            "is_admin": request.user == group.admin
        })



class MyGroupAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        group = Group.objects.filter(admin=request.user).first()

        if not group:
            return Response({"has_group": False})

        return Response({
            "has_group": True,
            "group_id": group.id
        })
