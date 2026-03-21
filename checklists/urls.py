from django.urls import path

from . import views

app_name = "checklists"

urlpatterns = [
    path("<str:entity_type>/<int:entity_pk>/add/", views.checklist_add, name="checklist_add"),
    path("<int:pk>/delete/", views.checklist_delete, name="checklist_delete"),
    path("<int:checklist_pk>/items/add/", views.item_add, name="item_add"),
    path("items/<int:pk>/toggle/", views.item_toggle, name="item_toggle"),
    path("items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path("items/<int:pk>/delete/", views.item_delete, name="item_delete"),
]
