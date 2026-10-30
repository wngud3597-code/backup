from django.shortcuts import render

# Create your views here.

# 메인 페이지를 응답하는 함수

# view함수의 약속
    # 모든 view 함수는 반드시 첫번째 인자로 요청 객체(urls.py로 부터 받은)가 들어온다.
    # 매개변수 이름이 request일 필요는 없음. 하지만 다른 이름을 사용하지 않는다.
def index(request):
    # 메인 페이지 (템플릿)을 응답 데이터로 생성
    # 템플릿을 취합해서 최종적으로 만들어주는 함수
    return render(request, 'articles/index.html')
