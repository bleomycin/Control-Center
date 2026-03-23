from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("", views.chat_page, name="chat"),
    path("<int:session_id>/", views.chat_page, name="chat_session"),
    path("<int:session_id>/send/", views.send_message_view, name="send"),
    path("<int:session_id>/stream/", views.stream_message_view, name="stream"),
    path("new/", views.new_session, name="new_session"),
    path("<int:session_id>/delete/", views.delete_session, name="delete_session"),
    path("<int:session_id>/rename/", views.rename_session, name="rename_session"),
    path("<int:session_id>/retry/<int:message_id>/", views.retry_message, name="retry_message"),
    path("<int:session_id>/edit/<int:message_id>/", views.edit_message, name="edit_message"),
    path("<int:session_id>/prune/", views.prune_history, name="prune"),
    path("sessions/", views.session_list, name="session_list"),
    path("process-email/", views.process_email_form, name="process_email"),
    path("gmail-search/", views.gmail_thread_search, name="gmail_thread_search"),
    path("gmail-thread/", views.gmail_thread_fetch, name="gmail_thread_fetch"),
    path("settings/", views.assistant_settings, name="settings"),
]
