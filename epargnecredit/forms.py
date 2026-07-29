from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from accounts.models import CustomUser

from .models import (
    Group,
    GroupMember,
    PretDemande,
    Versement,
)


User = get_user_model()


# =========================================================
# CRÉATION DE GROUPE
# =========================================================

class GroupForm(forms.ModelForm):

    class Meta:
        model = Group
        fields = [
            "nom",
            "montant_base",
        ]

        widgets = {
            "nom": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nom du groupe",
                    "required": True,
                    "autofocus": True,
                }
            ),
            "montant_base": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Montant de base (ex : 5000)",
                    "min": "1",
                    "step": "1",
                    "required": True,
                }
            ),
        }

        labels = {
            "nom": "Nom du groupe",
            "montant_base": "Montant de base du groupe (FCFA)",
        }

        help_texts = {
            "montant_base": (
                "Indiquez le montant minimal que chaque membre doit verser."
            ),
        }

    def clean_montant_base(self):
        montant = self.cleaned_data.get("montant_base")

        if montant is None:
            raise forms.ValidationError(
                "Veuillez saisir le montant de base."
            )

        if montant <= 0:
            raise forms.ValidationError(
                "Le montant de base doit être supérieur à zéro."
            )

        return montant


# =========================================================
# AJOUT D’UN MEMBRE
# =========================================================

class GroupMemberForm(forms.ModelForm):

    user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        label="Utilisateur",
        empty_label="Sélectionnez un utilisateur",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    class Meta:
        model = GroupMember
        fields = [
            "user",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["user"].label_from_instance = (
            lambda obj: (
                f"{getattr(obj, 'nom', str(obj))} "
                f"({getattr(obj, 'phone', '')})"
            )
        )


# =========================================================
# VERSEMENT
# =========================================================

class VersementForm(forms.ModelForm):

    class Meta:
        model = Versement
        fields = [
            "member",
            "montant",
            "methode",
        ]

        widgets = {
            "member": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "montant": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "step": "1",
                    "placeholder": "Ex : 5000",
                }
            ),
            "methode": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
        }

        labels = {
            "member": "Membre",
            "montant": "Montant (FCFA)",
            "methode": "Méthode de paiement",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["methode"].choices = [
            ("paydunya", "PayDunya"),
            ("caisse", "Caisse (sans frais)"),
        ]

    def clean_montant(self):
        montant = self.cleaned_data.get("montant")

        if montant is None:
            raise forms.ValidationError(
                "Veuillez saisir le montant du versement."
            )

        montant = Decimal(montant).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

        if montant <= 0:
            raise forms.ValidationError(
                "Le montant du versement doit être supérieur à zéro."
            )

        return montant


# =========================================================
# INSCRIPTION D’UN UTILISATEUR
# =========================================================

class RegisterForm(UserCreationForm):

    alias = forms.CharField(
        required=False,
        label="Alias (facultatif)",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Alias (facultatif)",
            }
        ),
    )

    class Meta:
        model = CustomUser

        fields = [
            "nom",
            "alias",
            "phone",
            "password1",
            "password2",
        ]

        widgets = {
            "nom": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Votre nom complet",
                    "autofocus": True,
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Votre numéro de téléphone",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["password1"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Mot de passe",
            }
        )

        self.fields["password2"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Confirmez le mot de passe",
            }
        )

    def save(self, commit=True):
        user = super().save(commit=False)

        user.alias = self.cleaned_data.get("alias", "").strip()

        if commit:
            user.save()

        return user


# =========================================================
# DEMANDE DE PRÊT
# =========================================================

class PretDemandeForm(forms.ModelForm):

    class Meta:
        model = PretDemande

        fields = [
            "montant",
            "interet",
            "penalite",
            "nb_mois",
            "debut_remboursement",
        ]

        widgets = {
            "montant": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "step": "1",
                    "placeholder": "Ex : 100000",
                }
            ),
            "interet": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "max": "100",
                    "step": "0.01",
                    "placeholder": "Ex : 5",
                }
            ),
            "penalite": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "max": "100",
                    "step": "0.01",
                    "placeholder": "Ex : 10",
                }
            ),
            "nb_mois": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "step": "1",
                    "placeholder": "Ex : 12",
                }
            ),
            "debut_remboursement": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
        }

        labels = {
            "montant": "Montant (FCFA)",
            "interet": "Intérêt (%)",
            "penalite": "Pénalité (%)",
            "nb_mois": "Nombre de mois",
            "debut_remboursement": "Début du remboursement",
        }

        help_texts = {
            "penalite": (
                "Pourcentage appliqué en cas de retard de remboursement."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Empêche la sélection d’une date passée côté navigateur.
        self.fields["debut_remboursement"].widget.attrs["min"] = (
            timezone.localdate().isoformat()
        )

    def clean_montant(self):
        montant = self.cleaned_data.get("montant")

        if montant is None:
            raise forms.ValidationError(
                "Veuillez saisir le montant du prêt."
            )

        try:
            montant = Decimal(montant).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError):
            raise forms.ValidationError(
                "Le montant saisi est invalide."
            )

        if montant <= 0:
            raise forms.ValidationError(
                "Le montant doit être supérieur à zéro."
            )

        return montant

    def clean_interet(self):
        interet = self.cleaned_data.get("interet")

        if interet is None:
            raise forms.ValidationError(
                "Veuillez saisir le taux d’intérêt."
            )

        try:
            interet = Decimal(interet)
        except (InvalidOperation, TypeError, ValueError):
            raise forms.ValidationError(
                "Le taux d’intérêt est invalide."
            )

        if interet < 0 or interet > 100:
            raise forms.ValidationError(
                "Le taux d’intérêt doit être compris entre 0 et 100 %."
            )

        return interet

    def clean_penalite(self):
        penalite = self.cleaned_data.get("penalite")

        if penalite is None:
            raise forms.ValidationError(
                "Veuillez saisir le taux de pénalité."
            )

        try:
            penalite = Decimal(penalite)
        except (InvalidOperation, TypeError, ValueError):
            raise forms.ValidationError(
                "Le taux de pénalité est invalide."
            )

        if penalite < 0 or penalite > 100:
            raise forms.ValidationError(
                "La pénalité doit être comprise entre 0 et 100 %."
            )

        return penalite

    def clean_nb_mois(self):
        nb_mois = self.cleaned_data.get("nb_mois")

        if nb_mois is None:
            raise forms.ValidationError(
                "Veuillez saisir le nombre de mois."
            )

        if nb_mois <= 0:
            raise forms.ValidationError(
                "Le nombre de mois doit être supérieur à zéro."
            )

        return nb_mois

    def clean_debut_remboursement(self):
        debut = self.cleaned_data.get("debut_remboursement")

        if debut is None:
            raise forms.ValidationError(
                "Veuillez sélectionner la date de début du remboursement."
            )

        if debut < timezone.localdate():
            raise forms.ValidationError(
                "La date de début du remboursement ne peut pas être passée."
            )

        return debut