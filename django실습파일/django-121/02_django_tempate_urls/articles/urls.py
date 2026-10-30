from django.urls import path
from . import views


# url 이름 앞에 붙이는 키워드 (태그)
app_name = 'articles'
urlpatterns = [
    # path('articles/', articles/로 요청이 들어왔을때 호출 할 view 함수를 작성)
    # articles/ 주소로 요청이 오면 index 뷰함수를 호출 하겠다.
    # index를 index() 괄호를 작성하지 않은 이유
        # view함수의 호출은 왼쪽 인자 주소로 요청이 "왔을때" 호출이 되어야하기 때문에 함수 주소만 기록해 둠
    path('', views.index, name='index'),
    # 주소 문자열과 view 함수 이름은 맞출 필요는 없다. 다만, 일반적으로 맞추는 편이다.
    # view 함수 이름과 path 이름은 맞출 필요는 없다. 다만, 일반적으로 맞추는 편이다.
    path('dinner/', views.dinner, name='dinner'),
    path('seach/', views.search, name='search'),
    path('throw/', views.throw, name='throw'),
    path('catch/', views.catch, name='catch'),
    path('detail/<int:num>/', views.detail, name='detail'),
]
