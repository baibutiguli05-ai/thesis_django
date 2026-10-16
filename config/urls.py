from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'Univer Thesis — Django әкімшісі'
admin.site.site_title = 'Univer Thesis'

urlpatterns = [
    path('admin/', admin.site.urls),          # Django-ның кіріктірілген әкімші панелі
    path('api/', include('thesis.api_urls')), # REST API
    path('api-auth/', include('rest_framework.urls')),
    path('', include('thesis.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
