from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('stakeholders/', include('stakeholders.urls')),
    path('assets/', include('assets.urls')),
    path('legal/', include('legal.urls')),
    path('tasks/', include('tasks.urls')),
    path('cashflow/', include('cashflow.urls')),
    path('notes/', include('notes.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
