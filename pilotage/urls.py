from django.urls import path

from . import views

app_name = "pilotage"

urlpatterns = [
    path(
        "executive-dashboard/",
        views.executive_dashboard,
        name="executive_dashboard",
    ),

    path(
        "executive-dashboard/data/",
        views.executive_dashboard_data,
        name="executive_dashboard_data",
    ),
]