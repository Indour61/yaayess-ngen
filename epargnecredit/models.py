from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import uuid
from django.db.models import Sum


# =========================================================
# GROUPE
# =========================================================

class Group(models.Model):

    nom = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_reset = models.DateTimeField(null=True, blank=True)

    code_invitation = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invitation_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="groupes_administres_ec"
    )

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    montant_base = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    montant_fixe_gagnant = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)

    prochain_gagnant = models.ForeignKey(
        "GroupMember",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="groupes_prochain_gagnant_ec"
    )

    membres_ec = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="GroupMember",
        related_name="groupes_ec"
    )

    is_remboursement = models.BooleanField(default=False)

    parent_group = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="remboursement_children"
    )

    class Meta:
        ordering = ["-date_creation"]
        db_table = "epargnecredit_group"

    def __str__(self):
        suffix = " (remboursement)" if self.is_remboursement else ""
        return f"{self.nom}{suffix}"

    # =============================
    # FINANCE
    # =============================

    @property
    def total_versements_valides(self):
        return (
            Versement.objects.filter(
                member__group=self,
                statut="VALIDE"
            ).aggregate(total=Sum("montant"))["total"] or Decimal("0")
        )

    @property
    def total_prets_approuves(self):
        return (
            PretDemande.objects.filter(
                member__group=self,
                statut="APPROVED"
            ).aggregate(total=Sum("montant"))["total"] or Decimal("0")
        )

    @property
    def caisse_disponible(self):
        return self.total_versements_valides - self.total_prets_approuves

    def get_remboursement_group(self):
        return self.remboursement_children.filter(is_remboursement=True).first()


# =========================================================
# MEMBRE
# =========================================================

class GroupMember(models.Model):

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="members_ec"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="groupmembers_ec"
    )

    alias = models.CharField(max_length=100, blank=True, null=True)

    montant = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    actif = models.BooleanField(default=True)
    exit_liste = models.BooleanField(default=False)

    date_ajout = models.DateTimeField(auto_now_add=True)
    date_joined = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "epargnecredit_groupmember"
        unique_together = ("group", "user")

    def __str__(self):
        return f"{self.user} - {self.group.nom}"


# =========================================================
# VERSEMENT
# =========================================================

class Versement(models.Model):

    STATUT_CHOICES = (
        ("EN_ATTENTE", "En attente"),
        ("VALIDE", "Validé"),
        ("REFUSE", "Refusé"),
    )

    member = models.ForeignKey(
        GroupMember,
        on_delete=models.CASCADE,
        related_name="versements_ec"
    )

    montant = models.DecimalField(max_digits=12, decimal_places=0)

    frais = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=Decimal("0")
    )

    methode = models.CharField(max_length=20, default="CAISSE")

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="EN_ATTENTE"
    )

    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="versements_valides_ec"
    )

    numero_recu = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True
    )

    transaction_id = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "epargnecredit_versement"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.member.user} - {self.montant} FCFA"

    @property
    def montant_total(self):
        return (self.montant or 0) + (self.frais or 0)

    def save(self, *args, **kwargs):

        if not self.frais:
            self.frais = (self.montant * Decimal("0.01")).quantize(Decimal("1"))

        if not self.numero_recu:
            self.numero_recu = f"EC-{uuid.uuid4().hex[:10].upper()}"

        super().save(*args, **kwargs)

    def valider(self, admin_user):
        if self.statut != "VALIDE":
            self.statut = "VALIDE"
            self.valide_par = admin_user
            self.date_validation = timezone.now()
            self.save()

    def refuser(self, admin_user):
        if self.statut != "REFUSE":
            self.statut = "REFUSE"
            self.valide_par = admin_user
            self.date_validation = timezone.now()
            self.save()


# =========================================================
# ACTION LOG
# =========================================================

class ActionLog(models.Model):

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="action_logs_ec",
        null=True,
        blank=True
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actionlogs_ec"
    )

    action = models.TextField()
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        db_table = "epargnecredit_actionlog"

    def __str__(self):
        return f"{self.date} - {self.user}"


# =========================================================
# INVITATION
# =========================================================

class Invitation(models.Model):

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="invitations_ec")
    phone = models.CharField(max_length=20)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "epargnecredit_invitation"

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(days=7)

    def __str__(self):
        return f"Invitation {self.phone} - {self.group.nom}"


# =========================================================
# DEMANDE DE PRET
# =========================================================

class PretDemande(models.Model):

    STATUTS = (
        ("PENDING", "En attente"),
        ("APPROVED", "Approuvé"),
        ("REJECTED", "Refusé"),
    )

    member = models.ForeignKey(
        GroupMember,
        on_delete=models.CASCADE,
        related_name="demandes_pret_ec"
    )

    montant = models.DecimalField(max_digits=12, decimal_places=0)
    interet = models.DecimalField(max_digits=5, decimal_places=2)
    penalite = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        verbose_name="Pénalité (%)"
    )
    nb_mois = models.PositiveIntegerField()
    debut_remboursement = models.DateField()

    statut = models.CharField(max_length=10, choices=STATUTS, default="PENDING")

    commentaire = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    decided_at = models.DateTimeField(null=True, blank=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prets_decides_ec"
    )

    class Meta:
        db_table = "epargnecredit_pretdemande"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Demande prêt {self.member.user} - {self.montant} FCFA"

    @property
    def total_a_rembourser(self):
        return self.montant + (self.montant * (self.interet / 100))

    @property
    def mensualite(self):
        return (self.total_a_rembourser / self.nb_mois) if self.nb_mois else self.total_a_rembourser

@property
def montant_penalite(self):
    return self.total_a_rembourser * (
        self.penalite / Decimal("100")
    )
@property
def total_avec_penalite(self):
    return self.total_a_rembourser + self.montant_penalite

# =========================================================
# REMBOURSEMENT PRET
# =========================================================

class PretRemboursement(models.Model):

    STATUT_CHOICES = (
        ("EN_ATTENTE", "En attente"),
        ("VALIDE", "Validé"),
        ("REFUSE", "Refusé"),
    )

    pret = models.ForeignKey(
        PretDemande,
        on_delete=models.CASCADE,
        related_name="remboursements"
    )

    montant = models.DecimalField(max_digits=12, decimal_places=0)

    methode = models.CharField(max_length=20, default="CAISSE")

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="EN_ATTENTE"
    )

    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remboursements_valides"
    )

    transaction_id = models.CharField(max_length=255, null=True, blank=True)

    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "epargnecredit_pret_remboursement"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Remboursement {self.pret.member.user} - {self.montant} FCFA"
