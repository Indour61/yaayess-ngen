from decimal import Decimal
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


# =========================================================
# GROUPE
# =========================================================

class Group(models.Model):

    nom = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_reset = models.DateTimeField(null=True, blank=True)

    code_invitation = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    invitation_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="groupes_administres_ec",
    )

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )

    montant_base = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
    )

    montant_fixe_gagnant = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        null=True,
        blank=True,
    )

    prochain_gagnant = models.ForeignKey(
        "GroupMember",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="groupes_prochain_gagnant_ec",
    )

    membres_ec = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="GroupMember",
        related_name="groupes_ec",
    )

    is_remboursement = models.BooleanField(default=False)

    parent_group = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="remboursement_children",
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
            Versement.objects
            .filter(
                member__group=self,
                statut="VALIDE",
            )
            .aggregate(total=Sum("montant"))["total"]
            or Decimal("0")
        )

    @property
    def total_prets_approuves(self):
        return (
            PretDemande.objects
            .filter(
                member__group=self,
                statut="APPROVED",
            )
            .aggregate(total=Sum("montant"))["total"]
            or Decimal("0")
        )

    @property
    def caisse_disponible(self):
        return (
            self.total_versements_valides
            - self.total_prets_approuves
        )

    def get_remboursement_group(self):
        return (
            self.remboursement_children
            .filter(is_remboursement=True)
            .first()
        )


# =========================================================
# MEMBRE
# =========================================================

class GroupMember(models.Model):

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="members_ec",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="groupmembers_ec",
    )

    alias = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    montant = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
    )

    actif = models.BooleanField(default=True)
    exit_liste = models.BooleanField(default=False)

    date_ajout = models.DateTimeField(auto_now_add=True)
    date_joined = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "epargnecredit_groupmember"
        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"],
                name="unique_epargnecredit_group_member",
            ),
        ]

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
        ("ANNULE", "Annulé"),
        ("ECHEC", "Échec"),
    )

    METHODE_CHOICES = (
        ("CAISSE", "Caisse"),
        ("MANUEL", "Manuel"),
        ("PAYDUNYA", "PayDunya"),
    )

    member = models.ForeignKey(
        GroupMember,
        on_delete=models.CASCADE,
        related_name="versements_ec",
    )

    montant = models.DecimalField(
        max_digits=12,
        decimal_places=0,
    )

    frais = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=Decimal("0"),
    )

    methode = models.CharField(
        max_length=20,
        choices=METHODE_CHOICES,
        default="CAISSE",
    )

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="EN_ATTENTE",
    )

    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="versements_valides_ec",
    )

    numero_recu = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
    )

    transaction_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )

    paydunya_token = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
    )

    paydunya_invoice_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
    )

    paydunya_status = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )

    paydunya_response = models.JSONField(
        null=True,
        blank=True,
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_paiement = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "epargnecredit_versement"
        ordering = ["-date_creation"]
        indexes = [
            models.Index(
                fields=["member", "statut"],
                name="ec_vers_member_stat_idx",
            ),
            models.Index(
                fields=["methode", "statut"],
                name="ec_vers_method_stat_idx",
            ),
        ]

    def __str__(self):
        return f"{self.member.user} - {self.montant} FCFA"

    @property
    def montant_total(self):
        return (
            Decimal(str(self.montant or 0))
            + Decimal(str(self.frais or 0))
        )

    def calculer_frais(self, taux=Decimal("1.00")):
        return (
            Decimal(str(self.montant or 0))
            * Decimal(str(taux))
            / Decimal("100")
        ).quantize(Decimal("1"))

    def save(self, *args, **kwargs):
        if (
            self.methode == "PAYDUNYA"
            and not self.frais
            and self.montant
        ):
            self.frais = self.calculer_frais()

        if not self.numero_recu:
            self.numero_recu = (
                f"EC-{uuid.uuid4().hex[:10].upper()}"
            )

        super().save(*args, **kwargs)

    def valider(self, admin_user=None):
        if self.statut == "VALIDE":
            return False

        maintenant = timezone.now()

        self.statut = "VALIDE"
        self.valide_par = admin_user
        self.date_validation = maintenant
        self.date_paiement = self.date_paiement or maintenant

        self.save(
            update_fields=[
                "statut",
                "valide_par",
                "date_validation",
                "date_paiement",
            ]
        )

        return True

    def refuser(self, admin_user=None):
        if self.statut == "REFUSE":
            return False

        self.statut = "REFUSE"
        self.valide_par = admin_user
        self.date_validation = timezone.now()

        self.save(
            update_fields=[
                "statut",
                "valide_par",
                "date_validation",
            ]
        )

        return True


# =========================================================
# ACTION LOG
# =========================================================

class ActionLog(models.Model):

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="action_logs_ec",
        null=True,
        blank=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actionlogs_ec",
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

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="invitations_ec",
    )

    phone = models.CharField(max_length=20)

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "epargnecredit_invitation"

    def is_expired(self):
        return (
            timezone.now()
            > self.created_at + timezone.timedelta(days=7)
        )

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
        ("CLOSED", "Soldé"),
    )

    member = models.ForeignKey(
        GroupMember,
        on_delete=models.CASCADE,
        related_name="demandes_pret_ec",
    )

    montant = models.DecimalField(
        max_digits=12,
        decimal_places=0,
    )

    interet = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    penalite = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        verbose_name="Pénalité (%)",
    )

    nb_mois = models.PositiveIntegerField()
    debut_remboursement = models.DateField()

    statut = models.CharField(
        max_length=10,
        choices=STATUTS,
        default="PENDING",
    )

    commentaire = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prets_decides_ec",
    )

    class Meta:
        db_table = "epargnecredit_pretdemande"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Demande prêt {self.member.user} "
            f"- {self.montant} FCFA"
        )

    @property
    def total_a_rembourser(self):
        montant = Decimal(str(self.montant or 0))
        interet = Decimal(str(self.interet or 0))

        return montant + (
            montant
            * interet
            / Decimal("100")
        )

    @property
    def mensualite(self):
        if self.nb_mois:
            return (
                self.total_a_rembourser
                / Decimal(str(self.nb_mois))
            )

        return self.total_a_rembourser

    @property
    def montant_penalite(self):
        taux_penalite = Decimal(str(self.penalite or 0))

        return (
            self.total_a_rembourser
            * taux_penalite
            / Decimal("100")
        )

    @property
    def total_avec_penalite(self):
        return (
            self.total_a_rembourser
            + self.montant_penalite
        )


# =========================================================
# REMBOURSEMENT PRET
# =========================================================

class PretRemboursement(models.Model):

    STATUT_CHOICES = (
        ("EN_ATTENTE", "En attente"),
        ("VALIDE", "Validé"),
        ("REFUSE", "Refusé"),
        ("ANNULE", "Annulé"),
        ("ECHEC", "Échec"),
    )

    METHODE_CHOICES = (
        ("CAISSE", "Caisse"),
        ("MANUEL", "Manuel"),
        ("PAYDUNYA", "PayDunya"),
    )

    pret = models.ForeignKey(
        PretDemande,
        on_delete=models.CASCADE,
        related_name="remboursements",
    )

    # Montant réellement affecté au remboursement du prêt.
    montant = models.DecimalField(
        max_digits=12,
        decimal_places=0,
    )

    # Frais plateforme supportés par le payeur.
    frais = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=Decimal("0"),
    )

    methode = models.CharField(
        max_length=20,
        choices=METHODE_CHOICES,
        default="CAISSE",
    )

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="EN_ATTENTE",
    )

    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remboursements_valides",
    )

    transaction_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )

    paydunya_token = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
    )

    paydunya_invoice_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
    )

    paydunya_status = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )

    paydunya_response = models.JSONField(
        null=True,
        blank=True,
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_paiement = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "epargnecredit_pret_remboursement"
        ordering = ["-date_creation"]
        indexes = [
            models.Index(
                fields=["pret", "statut"],
                name="ec_remb_pret_stat_idx",
            ),
            models.Index(
                fields=["methode", "statut"],
                name="ec_remb_method_stat_idx",
            ),
        ]

    def __str__(self):
        return (
            f"Remboursement {self.pret.member.user} "
            f"- {self.montant} FCFA"
        )

    @property
    def montant_total(self):
        return (
            Decimal(str(self.montant or 0))
            + Decimal(str(self.frais or 0))
        )

    def calculer_frais(self, taux=Decimal("1.00")):
        return (
            Decimal(str(self.montant or 0))
            * Decimal(str(taux))
            / Decimal("100")
        ).quantize(Decimal("1"))

    def save(self, *args, **kwargs):
        if (
            self.methode == "PAYDUNYA"
            and not self.frais
            and self.montant
        ):
            self.frais = self.calculer_frais()

        super().save(*args, **kwargs)

    def valider(self, utilisateur=None):
        """
        Valide le remboursement de façon idempotente.

        Retourne True si le statut a été modifié,
        False si le remboursement était déjà validé.
        """

        if self.statut == "VALIDE":
            return False

        maintenant = timezone.now()

        self.statut = "VALIDE"
        self.valide_par = utilisateur
        self.date_validation = maintenant
        self.date_paiement = self.date_paiement or maintenant

        self.save(
            update_fields=[
                "statut",
                "valide_par",
                "date_validation",
                "date_paiement",
            ]
        )

        return True

    def refuser(self, utilisateur=None):
        if self.statut == "REFUSE":
            return False

        self.statut = "REFUSE"
        self.valide_par = utilisateur
        self.date_validation = timezone.now()

        self.save(
            update_fields=[
                "statut",
                "valide_par",
                "date_validation",
            ]
        )

        return True
