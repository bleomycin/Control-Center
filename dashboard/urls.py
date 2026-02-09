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
]
