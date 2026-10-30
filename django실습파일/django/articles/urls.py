from django.urls import path
from . import views


# 프로젝트의 urls.py에서 articles/를 처리한 뒤, 나머지 주소를 여기서 찾는다.
urlpatterns = [
    # 'articles/index/' 주소로 요청이 오면 index 뷰 함수를 호출한다.
    # views.index에 괄호를 붙여 views.index()로 작성하지 않는 이유:
    # 함수 자체를 전달해야 Django가 해당 주소로 요청이 왔을 때 호출할 수 있기 때문이다.
    path('index/', views.index, name='index'),
    # 주소 문자열과 뷰 함수 이름은 같을 필요가 없다.
    # 다만 일반적으로는 알아보기 쉽게 맞추는 편이다.
    path('dinner/', views.dinner, name='dinner'),
    path('search/', views.search, name='search'),
    path('throw/', views.throw, name='throw'),
    path('catch/', views.catch, name='catch'),
    # <int:num>은 URL의 숫자를 정수로 바꿔 detail 함수의 num 인자로 전달한다.
    # Path Converter의 변수명과 뷰 함수의 매개변수 이름은 같아야 한다.
    path('detail/<int:num>/', views.detail, name='detail'),
    # <str:name>은 URL의 이름을 문자열로 받아 greeting 함수의 name 인자로 전달한다.
    path('hello/<str:name>/', views.greeting, name='greeting'),
]
