from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('register/verify/', views.register_verify_view, name='register_verify'),
    path('register/password/', views.register_password_view, name='register_password'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('forgot-password/verify/', views.forgot_password_verify_view, name='forgot_password_verify'),
    path('forgot-password/reset/', views.forgot_password_reset_view, name='forgot_password_reset'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.chat_page, name='chat_page'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('api/chat/', views.chat_stream, name='chat_stream'),
    path('api/conversations/', views.conversations_list, name='conversations_list'),
    path('api/conversations/<int:pk>/', views.conversation_detail, name='conversation_detail'),
    path('api/transcribe/', views.transcribe_audio, name='transcribe_audio'),
    path('api/ask-hr/', views.ask_hr, name='ask_hr'),
    path('api/upload/', views.upload_document, name='upload_document'),
    path('view-document/', views.view_document, name='view_document'),  # Document viewer endpoint
]
