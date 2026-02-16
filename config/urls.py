from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('stakeholders/', include('stakeholders.urls')),
    path('assets/', include('assets.urls')),
    path('legal/', include('legal.urls')),
    path('tasks/', include('tasks.urls')),
    path('cashflow/', include('cashflow.urls')),
    path('notes/', include('notes.urls')),
    # Serve media files unconditionally (single-user app, no Nginx needed)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
