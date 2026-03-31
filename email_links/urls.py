from django.urls import path
from . import views

app_name = "email_links"

urlpatterns = [
    # Gmail search API (returns HTML partial)
    path("api/gmail-search/", views.gmail_search_html, name="gmail_search"),
    # Email body expansion
    path("api/body/<int:pk>/", views.email_body, name="email_body"),
    # Entity email link/unlink
    path("link/property/<int:pk>/", views.property_email_link, name="property_email_link"),
    path("unlink/property/<int:pk>/<int:email_pk>/", views.property_email_unlink, name="property_email_unlink"),
    path("link/investment/<int:pk>/", views.investment_email_link, name="investment_email_link"),
    path("unlink/investment/<int:pk>/<int:email_pk>/", views.investment_email_unlink, name="investment_email_unlink"),
    path("link/loan/<int:pk>/", views.loan_email_link, name="loan_email_link"),
    path("unlink/loan/<int:pk>/<int:email_pk>/", views.loan_email_unlink, name="loan_email_unlink"),
    path("link/lease/<int:pk>/", views.lease_email_link, name="lease_email_link"),
    path("unlink/lease/<int:pk>/<int:email_pk>/", views.lease_email_unlink, name="lease_email_unlink"),
    path("link/policy/<int:pk>/", views.policy_email_link, name="policy_email_link"),
    path("unlink/policy/<int:pk>/<int:email_pk>/", views.policy_email_unlink, name="policy_email_unlink"),
    path("link/vehicle/<int:pk>/", views.vehicle_email_link, name="vehicle_email_link"),
    path("unlink/vehicle/<int:pk>/<int:email_pk>/", views.vehicle_email_unlink, name="vehicle_email_unlink"),
    path("link/aircraft/<int:pk>/", views.aircraft_email_link, name="aircraft_email_link"),
    path("unlink/aircraft/<int:pk>/<int:email_pk>/", views.aircraft_email_unlink, name="aircraft_email_unlink"),
    path("link/stakeholder/<int:pk>/", views.stakeholder_email_link, name="stakeholder_email_link"),
    path("unlink/stakeholder/<int:pk>/<int:email_pk>/", views.stakeholder_email_unlink, name="stakeholder_email_unlink"),
    path("link/legal-matter/<int:pk>/", views.legal_matter_email_link, name="legal_matter_email_link"),
    path("unlink/legal-matter/<int:pk>/<int:email_pk>/", views.legal_matter_email_unlink, name="legal_matter_email_unlink"),
    path("link/note/<int:pk>/", views.note_email_link, name="note_email_link"),
    path("unlink/note/<int:pk>/<int:email_pk>/", views.note_email_unlink, name="note_email_unlink"),
    path("link/task/<int:pk>/", views.task_email_link, name="task_email_link"),
    path("unlink/task/<int:pk>/<int:email_pk>/", views.task_email_unlink, name="task_email_unlink"),
]
