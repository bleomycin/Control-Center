from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="index"),
    path("search/", views.global_search, name="search"),
    path("timeline/", views.activity_timeline, name="timeline"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("calendar/events/", views.calendar_events, name="calendar_events"),
    path("settings/email/", views.email_settings, name="email_settings"),
    path("settings/email/test/", views.test_email, name="test_email"),
    path("notifications/", views.notifications_list, name="notifications"),
    path("notifications/badge/", views.notifications_badge, name="notifications_badge"),
    path("notifications/mark-read/", views.notifications_mark_read, name="notifications_mark_read"),
    path("settings/", views.settings_hub, name="settings_hub"),
    path("settings/sample-data/load/", views.sample_data_load, name="sample_data_load"),
    path("settings/sample-data/remove/", views.sample_data_remove, name="sample_data_remove"),
    path("settings/choices/", views.choice_settings, name="choice_settings"),
    path("settings/choices/add/<str:category>/", views.choice_add, name="choice_add"),
    path("settings/choices/edit/<int:pk>/", views.choice_edit, name="choice_edit"),
    path("settings/choices/toggle/<int:pk>/", views.choice_toggle, name="choice_toggle"),
    path("settings/choices/move/<int:pk>/<str:direction>/", views.choice_move, name="choice_move"),
]
