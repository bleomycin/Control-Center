from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from dashboard.views import pwa_manifest, pwa_offline, pwa_service_worker

urlpatterns = [
    path('manifest.json', pwa_manifest, name='manifest'),
    path('sw.js', pwa_service_worker, name='service_worker'),
    path('offline/', pwa_offline, name='offline'),
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('stakeholders/', include('stakeholders.urls')),
    path('assets/', include('assets.urls')),
    path('legal/', include('legal.urls')),
    path('tasks/', include('tasks.urls')),
    path('cashflow/', include('cashflow.urls')),
    path('notes/', include('notes.urls')),
    path('healthcare/', include('healthcare.urls')),
    path('documents/', include('documents.urls')),
    path('emails/', include('email_links.urls')),
    path('checklists/', include('checklists.urls')),
    path('assistant/', include('assistant.urls')),
    # Serve media files unconditionally (single-user app, no Nginx needed)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
