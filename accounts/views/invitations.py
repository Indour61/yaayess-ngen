import random
import string

from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie


User = get_user_model()


# ==========================================================
# CONSTANTES
# ==========================================================

OPTION_TONTINE = "1"
OPTION_EC = "2"

OPTION_LABELS = {
    OPTION_TONTINE: "Cotisation & Tontine",
    OPTION_EC: "Épargne & Crédit",
}


# ==========================================================
# HELPERS UTILISATEUR
# ==========================================================

def _generate_alias(base_name: str) -> str:
    """
    Génère un alias à partir du nom + 4 chiffres.
    """
    base = (
        (base_name or "")
        .strip()
        .lower()
        .replace(" ", ".")
    )

    suffix = "".join(
        random.choices(
            string.digits,
            k=4,
        )
    )

    return f"{base}.{suffix}"


def _unique_alias_for(name: str) -> str:
    """
    Génère un alias unique.
    """
    alias = _generate_alias(name)

    while User.objects.filter(alias=alias).exists():
        alias = _generate_alias(name)

    return alias


def _normalize_phone(raw: str) -> str:
    """
    Normalise un numéro de téléphone :
    - supprime espaces et tirets ;
    - conserve éventuellement le + initial ;
    - conserve uniquement les chiffres.
    """

    value = (
        (raw or "")
        .strip()
        .replace(" ", "")
        .replace("-", "")
    )

    if value.startswith("+"):
        return "+" + "".join(
            char
            for char in value[1:]
            if char.isdigit()
        )

    return "".join(
        char
        for char in value
        if char.isdigit()
    )


# ==========================================================
# HELPERS GROUPE
# ==========================================================

def _get_field_names(model) -> set[str]:
    """
    Retourne la liste des noms de champs d'un modèle.
    """
    return {
        field.name
        for field in model._meta.get_fields()
    }


def _find_group_in_model(model, code: str):
    """
    Cherche un groupe avec plusieurs champs possibles :
    code_invitation, invitation_code, uuid, code, slug.
    """

    if model is None or not code:
        return None

    fields = _get_field_names(model)

    query = Q()

    for field_name in (
        "code_invitation",
        "invitation_code",
        "uuid",
        "code",
        "slug",
    ):
        if field_name in fields:
            query |= Q(**{field_name: code})

    if query:
        group = (
            model.objects
            .filter(query)
            .order_by("-id")
            .first()
        )

        if group:
            return group

    if code.isdigit() and "id" in fields:
        return (
            model.objects
            .filter(id=int(code))
            .first()
        )

    return None


def _resolve_group_by_code(code: str):
    """
    Recherche un groupe à partir d'un code d'invitation.
    """

    code = (code or "").strip()

    if not code:
        raise Http404(
            "Invitation ou groupe introuvable."
        )

    # ------------------------------------------------------
    # 1. Recherche directe dans les groupes
    # ------------------------------------------------------

    for app_label in (
        "epargnecredit",
        "cotisationtontine",
    ):
        try:
            group_model = apps.get_model(
                app_label,
                "Group",
            )
        except LookupError:
            continue

        group = _find_group_in_model(
            group_model,
            code,
        )

        if group:
            return group

    # ------------------------------------------------------
    # 2. Recherche via un modèle Invitation
    # ------------------------------------------------------

    for app_label in (
        "epargnecredit",
        "cotisationtontine",
        "accounts",
    ):
        try:
            invitation_model = apps.get_model(
                app_label,
                "Invitation",
            )
        except LookupError:
            continue

        fields = _get_field_names(
            invitation_model
        )

        query = Q()

        if "code" in fields:
            query |= Q(code=code)

        if "token" in fields:
            query |= Q(token=code)

        if "uuid" in fields:
            query |= Q(uuid=code)

        if not query:
            continue

        queryset = invitation_model.objects.filter(
            query
        )

        # select_related uniquement si le champ existe
        if "group" in fields:
            queryset = queryset.select_related(
                "group"
            )

        invitation = queryset.first()

        if (
            invitation
            and getattr(
                invitation,
                "group",
                None,
            )
        ):
            return invitation.group

    raise Http404(
        "Invitation ou groupe introuvable."
    )


def _add_member_to_group(
    request,
    user,
    group,
) -> None:
    """
    Ajoute l'utilisateur au groupe correspondant
    sans créer de doublon.
    """

    app_label = getattr(
        getattr(
            group,
            "_meta",
            None,
        ),
        "app_label",
        "",
    )

    try:
        member_model = apps.get_model(
            app_label,
            "GroupMember",
        )
    except LookupError:
        messages.error(
            request,
            "Type de groupe inconnu.",
        )
        return

    fields = _get_field_names(
        member_model
    )

    defaults = {}

    if "montant" in fields:
        defaults["montant"] = 0

    if "date_joined" in fields:
        defaults["date_joined"] = (
            timezone.now()
        )

    if "actif" in fields:
        defaults["actif"] = True

    member, created = (
        member_model.objects.get_or_create(
            group=group,
            user=user,
            defaults=defaults,
        )
    )

    group_name = getattr(
        group,
        "nom",
        str(group.pk),
    )

    if created:
        messages.success(
            request,
            (
                "Vous avez été ajouté au groupe "
                f"« {group_name} »."
            ),
        )
    else:
        messages.info(
            request,
            (
                "Vous êtes déjà membre du groupe "
                f"« {group_name} »."
            ),
        )


def _forced_option_for_group(
    group,
) -> str | None:
    """
    Retourne l'option correspondant
    au type de groupe.
    """

    app_label = getattr(
        getattr(
            group,
            "_meta",
            None,
        ),
        "app_label",
        "",
    )

    if app_label == "cotisationtontine":
        return OPTION_TONTINE

    if app_label == "epargnecredit":
        return OPTION_EC

    return None


def _redirect_by_option(
    user,
    group=None,
) -> HttpResponse:
    """
    Redirige l'utilisateur vers le module adapté.
    """

    forced_option = (
        _forced_option_for_group(group)
        if group is not None
        else None
    )

    option = (
        forced_option
        or getattr(
            user,
            "option",
            None,
        )
    )

    # Synchronise l'option si nécessaire
    if (
        forced_option
        and getattr(
            user,
            "option",
            None,
        ) != forced_option
    ):
        user.option = forced_option

        try:
            user.save(
                update_fields=["option"]
            )
        except Exception:
            pass

    # ------------------------------------------------------
    # TONTINE
    # ------------------------------------------------------

    if option == OPTION_TONTINE:
        try:
            member_model = apps.get_model(
                "cotisationtontine",
                "GroupMember",
            )

            membership = (
                member_model.objects
                .filter(user=user)
                .order_by("-id")
                .first()
            )

            if membership:
                return redirect(
                    "cotisationtontine:group_detail",
                    membership.group.id,
                )

        except LookupError:
            pass

        return redirect(
            "cotisationtontine:"
            "dashboard_tontine_simple"
        )

    # ------------------------------------------------------
    # EPARGNE & CREDIT
    # ------------------------------------------------------

    try:
        member_model = apps.get_model(
            "epargnecredit",
            "GroupMember",
        )

        membership = (
            member_model.objects
            .filter(user=user)
            .order_by("-id")
            .first()
        )

        if membership:
            return redirect(
                "epargnecredit:group_detail",
                membership.group.id,
            )

    except LookupError:
        pass

    return redirect(
        "epargnecredit:"
        "dashboard_epargne_credit"
    )


# ==========================================================
# INSCRIPTION VIA INVITATION
# ==========================================================

@ensure_csrf_cookie
@csrf_protect
@transaction.atomic
def inscription_et_rejoindre(
    request: HttpRequest,
    code: str,
) -> HttpResponse:

    try:
        group = _resolve_group_by_code(
            code
        )

    except Http404:
        messages.error(
            request,
            (
                "Lien d’invitation invalide "
                "ou expiré."
            ),
        )

        return render(
            request,
            "accounts/inscription_par_invit.html",
            {
                "group": None,
                "forced_option": None,
                "option_labels": OPTION_LABELS,
            },
            status=404,
        )

    forced_option = (
        _forced_option_for_group(group)
        or OPTION_TONTINE
    )

    app_label = getattr(
        group._meta,
        "app_label",
        None,
    )

    is_ec_link = (
        app_label == "epargnecredit"
    )

    # ------------------------------------------------------
    # GET
    # ------------------------------------------------------

    if request.method == "GET":
        get_token(request)

        request.session[
            "__csrf_touch__"
        ] = timezone.now().isoformat()

        request.session.modified = True

        return render(
            request,
            "accounts/inscription_par_invit.html",
            {
                "group": group,
                "forced_option": forced_option,
                "option_labels": OPTION_LABELS,
            },
        )

    # ------------------------------------------------------
    # POST
    # ------------------------------------------------------

    nom = (
        request.POST.get("nom")
        or ""
    ).strip()

    phone = _normalize_phone(
        request.POST.get("phone")
    )

    password = (
        request.POST.get("password")
        or ""
    ).strip()

    confirm_password = (
        request.POST.get(
            "confirm_password"
        )
        or ""
    ).strip()

    # ------------------------------------------------------
    # VALIDATIONS
    # ------------------------------------------------------

    if not all(
        [
            nom,
            phone,
            password,
            confirm_password,
        ]
    ):
        messages.error(
            request,
            "Tous les champs sont requis.",
        )

        return render(
            request,
            "accounts/inscription_par_invit.html",
            {
                "group": group,
                "forced_option": forced_option,
                "option_labels": OPTION_LABELS,
            },
            status=400,
        )

    if password != confirm_password:
        messages.error(
            request,
            (
                "Les mots de passe ne "
                "correspondent pas."
            ),
        )

        return render(
            request,
            "accounts/inscription_par_invit.html",
            {
                "group": group,
                "forced_option": forced_option,
                "option_labels": OPTION_LABELS,
            },
            status=400,
        )

    # ------------------------------------------------------
    # CREATION / REJET UTILISATEUR
    # ------------------------------------------------------

    try:
        existing_user = (
            User.objects
            .filter(phone=phone)
            .first()
        )

        if existing_user:
            messages.error(
                request,
                (
                    "Ce numéro de téléphone existe "
                    "déjà. Veuillez vous connecter."
                ),
            )

            return render(
                request,
                "accounts/inscription_par_invit.html",
                {
                    "group": group,
                    "forced_option": forced_option,
                    "option_labels": OPTION_LABELS,
                },
                status=400,
            )

        alias = _unique_alias_for(
            nom
        )

        user = User.objects.create_user(
            nom=nom,
            phone=phone,
            password=password,
            alias=alias,
            option=forced_option,
        )

        # Validation automatique EC
        if is_ec_link:
            fields_to_update = []

            if hasattr(
                user,
                "is_validated",
            ):
                user.is_validated = True
                fields_to_update.append(
                    "is_validated"
                )

            user.option = OPTION_EC
            fields_to_update.append(
                "option"
            )

            user.save(
                update_fields=fields_to_update
            )

        login(
            request,
            user,
            backend=(
                "accounts.auth_backend."
                "PhoneBackend"
            ),
        )

        _add_member_to_group(
            request,
            user,
            group,
        )

        messages.success(
            request,
            (
                "Compte créé avec succès. "
                f"Bienvenue {nom} !"
            ),
        )

        return _redirect_by_option(
            user,
            group,
        )

    except IntegrityError:
        messages.error(
            request,
            (
                "Ce numéro est déjà utilisé. "
                "Essayez de vous connecter."
            ),
        )

        return render(
            request,
            "accounts/inscription_par_invit.html",
            {
                "group": group,
                "forced_option": forced_option,
                "option_labels": OPTION_LABELS,
            },
            status=400,
        )