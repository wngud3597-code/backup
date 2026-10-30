from django.shortcuts import render

from .models import Article


# Create your views here.
def index(request):
    """
    [메인 페이지]
    - 메인 페이지에는 전체 게시글 목록이 출력됨
    - 따라서 DB에서 전체 게시글을 가져와야 함
    - CRUD 중 READ : 전체 게시글 조회
    """
    # 1. DB에서 전체 게시글 조회
    #    - Article.objects.all() 의 결과는 QuerySet (게시글 객체들의 묶음)
    articles = Article.objects.all()

    # 2. 템플릿에 넘겨줄 데이터를 딕셔너리로 묶기
    #    - key('articles') => 템플릿에서 사용할 변수 이름
    #    - value(articles) => 실제로 전달되는 데이터
    context = {
        'articles': articles,
    }

    # 3. 템플릿(index.html)에 데이터(context)를 채워 HTML을 만들고, 응답으로 반환
    return render(request, 'articles/index.html', context)
