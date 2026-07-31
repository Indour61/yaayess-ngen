from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

from accounts.views import landing_view
from accounts.api.auth_views import MobileLoginView
from django.conf.urls.static import static

from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView
from accounts.jwt_serializer import PhoneTokenObtainPairSerializer

from core.views import robots_txt

from django.contrib import admin
from django.urls import include, path


# 🔐 JWT personnalisé
class PhoneTokenObtainPairView(TokenObtainPairView):
    serializer_class = PhoneTokenObtainPairSerializer


urlpatterns = [

    # 🔥 PAGE D’ACCUEIL (ROOT)
    path('', landing_view, name='landing'),

    # 🔐 AUTH (important pour éviter conflits)
    path('accounts/', include('accounts.urls')),

    # 📊 MODULES MÉTIER
    path('tontine/', include('cotisationtontine.urls')),
    path('epargne/', include('epargnecredit.urls')),

    # 🛠 ADMIN
    path('admin/', admin.site.urls),

    # 🔌 API
    path("api/mobile/login/", MobileLoginView.as_view(), name="mobile_login"),

    # 🔐 JWT
    path('api/token/', PhoneTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 🌐 SEO
    path("robots.txt", robots_txt),


    path('legal/', include('legal.urls')),

    path(
        "pilotage/",
        include("pilotage.urls"),
    ),

]


# 📁 MEDIA FILES
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

