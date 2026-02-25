from django.contrib import admin
from django.urls import path
from app01 import views
from app01.utils import send_code
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('article/<int:article_id>/', views.ArticleDetailView.as_view(), name='article_detail'),
    path('article/<int:article_id>/edit/', views.EditArticleView.as_view(), name='edit_article'),
    path('article/<int:article_id>/delete/', views.DeleteArticleView.as_view(), name='delete_article'),
    path('article/pub/', views.PubArticleView.as_view(), name='pub_article'),
    path('article/upload_image/', views.upload_article_image, name='upload_article_image'),
    path('tag/create/', views.create_tag, name='create_tag'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('profile/', views.PersonalCenterView.as_view(), name='profile'),
    path('dashboard/', views.DataDashboardView.as_view(), name='dashboard'),
    path('logout/', views.logout, name='logout'),
    path('send_email_captcha/', send_code.send_email_captcha, name='send_email_captcha'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
