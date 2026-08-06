from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import uuid


# =====================================================
# GROUPE TONTINE
# =====================================================

import uuid
from django.conf import settings
from django.db import models


class Group(models.Model):

    # -----------------------------
    # INFOS DE BASE
    # -----------------------------
    nom = models.CharField(max_length=255)

    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="groupes_administres_tontine"
    )

    group_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # -----------------------------
    # DATES
    # -----------------------------
    date_creation = models.DateTimeField(auto_now_add=True)
    date_reset = models.DateTimeField(null=True, blank=True)

    # -----------------------------
    # INVITATION
    # -----------------------------
    code_invitation = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invitation_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # -----------------------------
    # MONTANTS
    # -----------------------------
    montant_base = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    montant_fixe_gagnant = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        null=True,
        blank=True
    )

    # -----------------------------
    # GESTION DU CYCLE 🔥
    # -----------------------------
    cycle_numero = models.IntegerField(default=1)
    tour_actuel = models.IntegerField(default=1)

    is_active = models.BooleanField(default=True)
    cycle_termine = models.BooleanField(default=False)

    tirage_effectue = models.BooleanField(default=False)
    # -----------------------------
    # SUIVI DU GAGNANT
    # -----------------------------
    prochain_gagnant = models.ForeignKey(
        'GroupMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="groupes_prochain_gagnant"
    )

    # -----------------------------
    # CONFIGURATION
    # -----------------------------
    auto_reset = models.BooleanField(default=True)
    autoriser_ajout_membre = models.BooleanField(default=True)

    # -----------------------------
    # META
    # -----------------------------
    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.nom} (Cycle {self.cycle_numero} - Tour {self.tour_actuel})"

    # =====================================================
    # 🔥 MÉTHODES MÉTIER (ICI EN BAS ✅)
    # =====================================================

    def reset_apres_tirage(self):
        """
        🔥 Après chaque tirage :
        - passe au tour suivant
        """

        self.tour_actuel += 1
        self.is_active = True
        self.cycle_termine = False
        self.prochain_gagnant = None

        self.save()

    def total_membres(self):
        return self.membres.count()

    def total_cotise(self):
        """
        🔥 CORRECTION : basé sur Versement + tour
        """
        from .models import Versement
        from django.db.models import Sum

        return (
            Versement.objects
            .filter(
                member__group=self,
                statut="VALIDE",
                tour=self.tour_actuel
            )
            .aggregate(total=Sum("montant"))["total"] or 0
        )

    def cycle_est_termine(self):
        membres = self.membres.filter(actif=True, exit_liste=False)
        return all(m.a_recu for m in membres)

    def peut_cotiser(self):
        return self.is_active and not self.cycle_termine

# =====================================================
# 🔁 RESET COMPLET DU CYCLE
# =====================================================
def reset_cycle(self):
    """
    🔥 Reset complet :
    - remet les membres à zéro
    - réinitialise les tours
    - relance un nouveau cycle propre
    """

    membres = self.groupmember_set.all()

    for membre in membres:
        membre.montant = 0

        # 🔥 Sécurité
        if hasattr(membre, 'a_recu'):
            membre.a_recu = False

        membre.save()

    # 🔁 Nouveau cycle
    self.cycle_numero += 1

    # 🔥 TRÈS IMPORTANT
    self.tour_actuel = 1
    self.prochain_gagnant = None

    # 🔥 Réactivation propre
    self.cycle_termine = False
    self.is_active = True

    from django.utils import timezone
    self.date_reset = timezone.now()

    self.save()


# =====================================================
# 🔒 FIN DU CYCLE
# =====================================================
def verifier_et_cloturer_cycle(self):
    """
    Vérifie si tous les membres ont reçu leur tour
    et déclenche le reset si activé
    """

    # 🔒 Sécurité : éviter double exécution
    if self.cycle_termine:
        return

    membres_actifs = self.groupmember_set.filter(actif=True, exit_liste=False)

    if not membres_actifs.exists():
        return  # rien à faire

    # 🔍 Vérifie si tous ont reçu
    tous_ont_recu = all(
        getattr(m, "a_recu", False) for m in membres_actifs
    )

    if tous_ont_recu:

        # 🔒 Clôturer cycle
        self.cycle_termine = True
        self.is_active = False
        self.prochain_gagnant = None
        self.save()

        # 🔁 Reset automatique si activé
        if self.auto_reset:
            self.reset_cycle()

# =====================================================
# MEMBRE
# =====================================================

from django.conf import settings
from django.db import models
from django.utils import timezone


class GroupMember(models.Model):

    group = models.ForeignKey(
        'Group',
        on_delete=models.CASCADE,
        related_name='membres'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    alias = models.CharField(max_length=100, blank=True, null=True)

    # 💰 montant cotisé dans le cycle en cours
    montant = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0
    )

    # 🔥 NOUVEAU : suivi du cycle
    a_recu = models.BooleanField(
        default=False,
        help_text="Indique si ce membre a déjà reçu la cagnotte dans ce cycle"
    )

    ordre_passage = models.IntegerField(
        null=True,
        blank=True,
        help_text="Ordre de passage dans la tontine (optionnel)"
    )

    # -----------------------------
    # STATUT
    # -----------------------------
    actif = models.BooleanField(default=True)
    exit_liste = models.BooleanField(default=False)

    # -----------------------------
    # DATES
    # -----------------------------
    date_ajout = models.DateTimeField(auto_now_add=True)
    date_joined = models.DateTimeField(default=timezone.now)

    # -----------------------------
    # META
    # -----------------------------
    class Meta:
        unique_together = ('group', 'user')
        ordering = ['date_ajout']

    # -----------------------------
    # STRING
    # -----------------------------
    def __str__(self):
        return f"{self.get_display_name()} - {self.group.nom}"

    # =====================================================
    # MÉTHODES UTILES 🔥
    # =====================================================

    def get_display_name(self):
        """
        Retourne alias ou nom utilisateur
        """
        return self.alias if self.alias else getattr(self.user, "nom", str(self.user))

    def peut_cotiser(self):
        """
        Vérifie si le membre peut cotiser
        """
        return (
            self.actif
            and not self.exit_liste
            and self.group.is_active
            and not self.group.cycle_termine
        )

    def reset_pour_nouveau_cycle(self):
        """
        Reset du membre pour un nouveau cycle
        """
        self.montant = 0
        self.a_recu = False
        self.save()

from decimal import Decimal
from django.db import models
from django.conf import settings

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models


class Versement(models.Model):

    STATUT_CHOICES = (
        ("EN_ATTENTE", "En attente"),
        ("VALIDE", "Validé"),
        ("REFUSE", "Refusé"),
    )

    METHODE_CHOICES = (
        ("WAVE", "Wave"),
        ("OM", "Orange Money"),
        ("CAISSE", "Caisse"),
        ("PAYDUNYA", "PayDunya"),
    )

    PAYDUNYA_STATUS_CHOICES = (
        ("pending", "En attente"),
        ("completed", "Terminé"),
        ("cancelled", "Annulé"),
        ("failed", "Échoué"),
    )

    member = models.ForeignKey(
        GroupMember,
        on_delete=models.CASCADE,
        related_name="versements",
    )

    # =====================================================
    # CYCLE ET TOUR
    # =====================================================

    tour = models.PositiveIntegerField(
        default=1,
        help_text="Numéro du tour de tontine",
    )

    cycle = models.PositiveIntegerField(
        default=1,
        help_text="Numéro du cycle",
    )

    # =====================================================
    # MONTANTS
    # =====================================================

    montant = models.DecimalField(
        max_digits=12,
        decimal_places=0,
    )

    frais = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=Decimal("0"),
    )

    # =====================================================
    # MÉTHODE DE PAIEMENT
    # =====================================================

    methode = models.CharField(
        max_length=20,
        choices=METHODE_CHOICES,
        default="WAVE",
    )

    preuve = models.ImageField(
        upload_to="preuves/",
        null=True,
        blank=True,
    )

    # =====================================================
    # STATUT YAAYESS
    # =====================================================

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="EN_ATTENTE",
        db_index=True,
    )

    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="versements_valides_tontine",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
    )

    date_validation = models.DateTimeField(
        null=True,
        blank=True,
    )

    note_admin = models.TextField(
        blank=True,
        null=True,
        help_text="Raison du refus ou commentaire",
    )

    # =====================================================
    # PAYDUNYA
    # =====================================================

    paydunya_token = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        unique=True,
        help_text="Token unique de la facture PayDunya",
    )

    paydunya_status = models.CharField(
        max_length=30,
        choices=PAYDUNYA_STATUS_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text="Statut transmis par PayDunya",
    )

    paydunya_invoice_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Adresse de la page de paiement PayDunya",
    )

    paydunya_receipt_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Adresse du reçu électronique PayDunya",
    )

    paydunya_customer_name = models.CharField(
        max_length=150,
        null=True,
        blank=True,
    )

    paydunya_customer_phone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    paydunya_customer_email = models.EmailField(
        null=True,
        blank=True,
    )

    paydunya_paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date de confirmation du paiement PayDunya",
    )

    paydunya_payload = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "Dernière réponse PayDunya conservée pour audit "
            "et rapprochement"
        ),
    )

    class Meta:
        ordering = ["-date_creation"]

        indexes = [
            models.Index(
                fields=["member", "tour"],
            ),
            models.Index(
                fields=["member", "cycle"],
            ),
            models.Index(
                fields=["tour", "cycle"],
            ),
            models.Index(
                fields=["member", "cycle", "tour", "statut"],
            ),
            models.Index(
                fields=["methode", "statut"],
            ),
        ]

    def __str__(self):
        return (
            f"{self.member.user} - {self.montant} FCFA "
            f"(Cycle {self.cycle} | Tour {self.tour}) "
            f"[{self.statut}]"
        )

    # =====================================================
    # ENREGISTREMENT AUTOMATIQUE
    # =====================================================

    def save(self, *args, **kwargs):
        """
        Calcule les frais YAAYESS et complète le cycle et le tour
        lorsqu'ils ne sont pas renseignés.
        """

        montant = Decimal(
            str(self.montant or 0)
        )

        if self.frais is None or Decimal(str(self.frais)) == 0:
            self.frais = (
                montant * Decimal("0.02")
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )

        if self.member_id:
            group = self.member.group

            if not self.cycle:
                self.cycle = group.cycle_numero

            if not self.tour:
                self.tour = group.tour_actuel

        super().save(*args, **kwargs)

    # =====================================================
    # PROPRIÉTÉS MÉTIER
    # =====================================================

    @property
    def montant_total(self):
        """
        Montant payé par le client :
        cotisation + frais YAAYESS.
        """
        montant = Decimal(
            str(self.montant or 0)
        )

        frais = Decimal(
            str(self.frais or 0)
        )

        return montant + frais

    @property
    def montant_a_payer(self):
        """
        Alias explicite utilisé lors de la création
        de la facture PayDunya.
        """
        return self.montant_total

    @property
    def est_paiement_paydunya(self):
        return self.methode == "PAYDUNYA"

    @property
    def est_paye_via_paydunya(self):
        return (
            self.methode == "PAYDUNYA"
            and self.statut == "VALIDE"
            and self.paydunya_status == "completed"
        )

    @property
    def recu_paydunya_disponible(self):
        return bool(
            self.est_paye_via_paydunya
            and self.paydunya_receipt_url
        )


# =====================================================
# TIRAGE (AVEC CYCLE NUMBER)
# =====================================================

class Tirage(models.Model):

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="tirages"
    )

    gagnant = models.ForeignKey(
        GroupMember,
        on_delete=models.CASCADE,
        related_name="tirages_gagnes"
    )

    montant = models.DecimalField(max_digits=12, decimal_places=0)

    cycle_number = models.PositiveIntegerField(default=1)

    # 🔥 AJOUT CRUCIAL (OBLIGATOIRE)
    tour = models.PositiveIntegerField(
        default=1,
        help_text="Numéro du tour dans le cycle"
    )

    date_tirage = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_tirage"]
        indexes = [
            models.Index(fields=["group", "cycle_number", "tour"]),
        ]

    def __str__(self):
        return f"{self.group.nom} | Cycle {self.cycle_number} | Tour {self.tour}"


# =====================================================
# HISTORIQUE ACTIONS
# =====================================================

class ActionLog(models.Model):

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="action_logs",
        null=True,
        blank=True
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    action = models.TextField()
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.user}"


class Cycle(models.Model):
    group = models.ForeignKey("Group", on_delete=models.CASCADE, related_name="cycles")

    # 🔥 AJOUT IMPORTANT
    numero = models.IntegerField(default=1)

    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()

    def __str__(self):
        return f"Cycle {self.numero} - {self.group.nom}"

    @property
    def total_etapes(self):
        return self.etapes.count()

    @property
    def completed_etapes(self):
        return self.etapes.filter(tirage__isnull=False).count()

    @property
    def progression(self):
        if self.total_etapes == 0:
            return 0
        return int((self.completed_etapes / self.total_etapes) * 100)


class EtapeCycle(models.Model):
    cycle = models.ForeignKey(Cycle, on_delete=models.CASCADE, related_name="etapes")
    numero_etape = models.IntegerField()
    date_etape = models.DateTimeField()

    tirage = models.ForeignKey(
        "Tirage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"Étape {self.numero_etape} - Cycle {self.cycle.id}"



# =====================================================
# INVITATION
# =====================================================

class Invitation(models.Model):

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="invitations"
    )

    phone = models.CharField(max_length=20)

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(days=7)

    def __str__(self):
        return f"Invitation {self.phone} - {self.group.nom}"
