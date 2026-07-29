from django.contrib import admin
from .models import Group, GroupMember, ActionLog


# =====================================================
# GROUP ADMIN
# =====================================================

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):

    list_display = (
        'nom',
        'admin_nom',
        'admin_phone',
        'montant_base',
        'cycle_numero',
        'is_active',
        'date_creation',
        'membres_count'
    )

    list_filter = (
        'date_creation',
        'is_active',
        'cycle_numero'
    )

    search_fields = ('nom', 'admin__nom', 'admin__phone')
    ordering = ('-date_creation',)

    readonly_fields = (
        'code_invitation',
        'invitation_token',
        'group_uuid',   # ✅ CORRIGÉ
        'date_creation',
        'date_reset'
    )

    fieldsets = (
        ('Informations de base', {
            'fields': (
                'nom',
                'admin',
                'montant_base',
                'montant_fixe_gagnant'
            )
        }),

        ('Cycle de tontine 🔥', {
            'fields': (
                'cycle_numero',
                'is_active',
                'cycle_termine',
                'auto_reset'
            )
        }),

        ('Dates', {
            'fields': (
                'date_creation',
                'date_reset'
            ),
            'classes': ('collapse',)
        }),

        ('Codes et tokens', {
            'fields': (
                'code_invitation',
                'invitation_token',
                'group_uuid'   # ✅ CORRIGÉ
            ),
            'classes': ('collapse',)
        }),

        ('Gagnants', {
            'fields': ('prochain_gagnant',),
            'classes': ('collapse',)
        }),
    )

    # -----------------------------
    # CUSTOM DISPLAY
    # -----------------------------
    def admin_nom(self, obj):
        return getattr(obj.admin, "nom", obj.admin)
    admin_nom.short_description = 'Admin (Nom)'

    def admin_phone(self, obj):
        return getattr(obj.admin, "phone", "-")
    admin_phone.short_description = 'Admin (Téléphone)'

    def membres_count(self, obj):
        return obj.membres.count()
#    def membres_count(self, obj):
#        return obj.groupmember_set.count()  # ✅ CORRIGÉ
#    membres_count.short_description = 'Nombre de membres'


# =====================================================
# GROUP MEMBER ADMIN
# =====================================================

@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):

    list_display = (
        'user_nom',
        'user_alias',
        'user_phone',
        'group',
        'montant',
        'a_recu',   # 🔥 IMPORTANT pour le cycle
        'actif',
        'exit_liste',
        'date_ajout'
    )

    list_filter = (
        'actif',
        'exit_liste',
        'a_recu',
        'group'
    )

    search_fields = ('user__nom', 'user__phone', 'group__nom')
    autocomplete_fields = ('user', 'group')

    readonly_fields = ('date_ajout', 'date_joined')

    list_editable = (
        'montant',
        'actif',
        'exit_liste',
        'a_recu'
    )

    fieldsets = (
        ('Informations de base', {
            'fields': (
                'user',
                'group',
                'montant'
            )
        }),

        ('Cycle tontine 🔥', {
            'fields': (
                'a_recu',
            )
        }),

        ('Statut', {
            'fields': (
                'actif',
                'exit_liste'
            )
        }),

        ('Dates', {
            'fields': (
                'date_ajout',
                'date_joined'
            ),
            'classes': ('collapse',)
        }),
    )

    # -----------------------------
    # CUSTOM DISPLAY
    # -----------------------------
    def user_nom(self, obj):
        return getattr(obj.user, "nom", obj.user)
    user_nom.short_description = 'Nom'

    def user_alias(self, obj):
        return getattr(obj.user, 'alias', '-')
    user_alias.short_description = 'Alias'

    def user_phone(self, obj):
        return getattr(obj.user, "phone", "-")
    user_phone.short_description = 'Téléphone'


# =====================================================
# ACTION LOG ADMIN
# =====================================================

@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'action',
        'date',
        'formatted_date'
    )

    list_filter = ('date', 'user')
    search_fields = ('user__nom', 'user__phone', 'action')
    ordering = ('-date',)

    readonly_fields = ('date',)

    def formatted_date(self, obj):
        return obj.date.strftime('%d/%m/%Y %H:%M')
    formatted_date.short_description = 'Date formatée'


