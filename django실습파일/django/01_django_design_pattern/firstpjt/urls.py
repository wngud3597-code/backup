"""
URL configuration for firstpjt project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from articles import views

urlpatterns = [
    path('admin/', admin.site.urls),
    # path('articles/', articles/로 요청이 들어왔을때 호출 할 view 함수를 작성)
    # articles/ 주소로 요청이 오면 index 뷰함수를 호출 하겠다.
    # index를 index() 괄호를 작성하지 않은 이유
        # view함수의 호출은 왼쪽 인자 주소로 요청이 "왔을때" 호출이 되어야하기 때문에 함수 주소만 기록해 둠
    path('articles/', views.index),
]
