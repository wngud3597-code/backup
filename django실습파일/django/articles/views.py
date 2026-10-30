from django.shortcuts import render

# Create your views here.

def index(request):
    # 메인페이지(템플릿)을 응답

    # 인덱스 템플릿에서 사용할 데이터를 정의
    # 딕셔너리 이름이 반드시 context일 필요는 없으나 보통은 context로 지정한다.
    context = {
        'name': 'Jane',
    }

    return render(request, 'articles/index.html', context)


import random


def dinner(request):
    foods = ['국밥', '국수', '카레', '탕수육', '빵',]
    picked = random.choice(foods)
    context = {
        'foods': foods,
        'picked': picked,
    }
    return render(request, 'articles/dinner.html', context)


def search(request):
    return render(request, 'articles/search.html')


# 클라이언트에게 데이터를 입력할 form이 담긴 페이지를 응답하는 함수
def throw(request):
    return render(request, 'articles/throw.html')


# 사용자 입력 데이터를 받아 그 데이터를 추출하여 어떤 데이터를 보냈는지 다시 알려주는 함수
def catch(request):
    # 1. 사용자가 입력한 데이터를 찾아야 함
    # 그런데 사용자가 입력한 데이터는 어디에 들어있을까?
    # 사실 클라이언트가 보낸 모든 정보는 첫 번째 인자(request)에 들어 있음
    # 찾은 데이터를 변수에 담아서
    # 입력칸의 name="message"와 같은 이름으로 GET 데이터를 가져옴
    message = request.GET.get('message', '')
    context = {
        'message': message,
    }
    # 템플릿과 함께 응답
    return render(request, 'articles/catch.html', context)


# URL에서 전달받은 정수 num을 템플릿에 전달하여 글 번호를 보여주는 함수
def detail(request, num):
    context = {
        'num': num,
    }
    return render(request, 'articles/detail.html', context)


# URL에서 전달받은 문자열 name을 템플릿에 전달하여 인사하는 함수
def greeting(request, name):
    context = {
        'name': name,
    }
    return render(request, 'articles/greeting.html', context)
