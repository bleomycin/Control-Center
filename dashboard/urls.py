from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="index"),
    path("version/<str:version>/", views.switch_dashboard_version, name="switch_version"),
    path("search/", views.global_search, name="search"),
    path("timeline/", views.activity_timeline, name="timeline"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("calendar/events/", views.calendar_events, name="calendar_events"),
    path("calendar/feed.ics", views.calendar_feed, name="calendar_feed"),
    path("settings/calendar-feed/", views.calendar_feed_settings, name="calendar_feed_settings"),
    path("settings/email/", views.email_settings, name="email_settings"),
    path("settings/email/test/", views.test_email, name="test_email"),
    path("notifications/", views.notifications_list, name="notifications"),
    path("notifications/badge/", views.notifications_badge, name="notifications_badge"),
    path("notifications/mark-read/", views.notifications_mark_read, name="notifications_mark_read"),
    path("settings/", views.settings_hub, name="settings_hub"),
    path("settings/sample-data/load/", views.sample_data_load, name="sample_data_load"),
    path("settings/sample-data/remove/", views.sample_data_remove, name="sample_data_remove"),
    path("settings/sample-data/load/<str:section>/", views.sample_data_load_section, name="sample_data_load_section"),
    path("settings/sample-data/remove/<str:section>/", views.sample_data_remove_section, name="sample_data_remove_section"),
    path("settings/sample-data/hard-reset/", views.sample_data_hard_reset, name="sample_data_hard_reset"),
    path("settings/choices/", views.choice_settings, name="choice_settings"),
    path("settings/choices/add/<str:category>/", views.choice_add, name="choice_add"),
    path("settings/choices/edit/<int:pk>/", views.choice_edit, name="choice_edit"),
    path("settings/choices/toggle/<int:pk>/", views.choice_toggle, name="choice_toggle"),
    path("settings/choices/move/<int:pk>/<str:direction>/", views.choice_move, name="choice_move"),
    path("settings/backups/", views.backup_settings, name="backup_settings"),
    path("settings/backups/config/", views.backup_config_update, name="backup_config_update"),
    path("settings/backups/create/", views.backup_create, name="backup_create"),
    path("settings/backups/download/<str:filename>/", views.backup_download, name="backup_download"),
    path("settings/backups/delete/<str:filename>/", views.backup_delete, name="backup_delete"),
    path("settings/backups/restore/<str:filename>/", views.backup_restore, name="backup_restore"),
    path("settings/backups/restore/", views.backup_restore, name="backup_restore_upload"),
]
