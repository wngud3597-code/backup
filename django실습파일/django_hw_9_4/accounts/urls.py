from django.urls import path
from . import views


app_name = 'accounts'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login, name='login'),
    path('signup/', views.signup, name='signup'),
    path('update/', views.update, name='update'),
    path('password/', views.change_password, name='change_password'),
    path('logout/', views.logout, name='logout'),
]