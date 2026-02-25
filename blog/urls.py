from django.contrib import admin
from django.urls import path, include

app_name = 'blog'

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', include('app01.urls')),
]
