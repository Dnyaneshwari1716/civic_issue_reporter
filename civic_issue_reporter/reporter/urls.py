from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_issue, name='upload_issue'),
    path('download-pdf/', views.download_complaint_pdf, name='download_complaint_pdf'),
     path('send-email/', views.send_email_to_authority, name='send_email_to_authority'),
     path('download/', views.download_complaint_pdf, name='download_pdf'), 
     path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('user/dashboard/', views.user_dashboard, name='user_dashboard'),
    path('authority/dashboard/', views.authority_dashboard, name='authority_dashboard'),
    path('', views.upload_issue, name='upload_issue'),
    path('download-pdf/', views.download_complaint_pdf, name='download_complaint_pdf'),
]
