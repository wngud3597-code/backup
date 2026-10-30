from django.shortcuts import redirect, render

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


def detail(request, article_pk):
    """
    [단일 게시글 조회]
    - URL에서 넘겨받은 article_pk로 몇 번 게시글을 볼지 결정
    - DB에서 해당 게시글 1개를 조회한 뒤 템플릿에 전달
    - CRUD 중 READ : 단일 게시글 조회
    """
    # 1. pk가 article_pk인 게시글 1개 조회
    #    - get()의 결과는 QuerySet이 아닌 Article 객체 1개
    article = Article.objects.get(pk=article_pk)

    # 2. 템플릿에 넘겨줄 데이터를 딕셔너리로 묶기
    context = {
        'article': article,
    }

    # 3. 템플릿(detail.html)에 데이터를 채워 HTML을 만들고, 응답으로 반환
    return render(request, 'articles/detail.html', context)


def new(request):
    """
    [게시글 작성 페이지] - create와 한 쌍 (GET)
    - 제목/내용을 입력할 form이 담긴 빈 페이지를 응답
    - DB 작업 없음 (아직 저장할 데이터가 없으므로)
    """
    return render(request, 'articles/new.html')


def create(request):
    """
    [게시글 저장] - new와 한 쌍 (POST)
    - new 페이지의 form에서 제출된 데이터를 받아 DB에 저장
    - CRUD 중 CREATE
    """
    # 1. form에서 제출된 제목과 내용 꺼내기
    #    - request.POST : form 데이터가 담긴 딕셔너리 형태의 객체
    #    - get('title') 의 'title' => input 태그의 name 속성 값
    title = request.POST.get('title')
    content = request.POST.get('content')

    # 2. Article 인스턴스 생성 후 DB에 저장
    #    - 인스턴스를 만든 것만으로는 저장되지 않음, save()를 호출해야 저장됨
    article = Article(title=title, content=content)
    article.save()

    # (사용하지 않는 방식) 저장 완료 페이지를 바로 render로 응답
    # => 이 화면에서 새로고침하면 POST 요청이 다시 전송되어 같은 글이 중복 저장됨
    # return render(request, 'articles/create.html')

    # 3. 방금 저장한 게시글의 상세 페이지로 redirect
    #    - 서버가 브라우저에게 "이 주소로 다시 요청해"라고 지시하는 응답
    #    - redirect('app_name:URL name', URL에 들어갈 값)
    #    - article.pk는 save() 이후에 생성되므로 이 시점에 사용 가능
    return redirect('articles:detail', article.pk)


def delete(request, article_pk):
    """
    [게시글 삭제]
    - 삭제할 게시글을 먼저 조회한 뒤 삭제
    - CRUD 중 DELETE
    """
    # 1. 삭제할 게시글 조회
    article = Article.objects.get(pk=article_pk)

    # 2. DB에서 삭제
    article.delete()

    # 3. 삭제된 글의 상세 페이지는 더 이상 없으므로 메인 페이지로 redirect
    return redirect('articles:index')


def edit(request, article_pk):
    """
    [게시글 수정 페이지] - update와 한 쌍 (GET)
    - 기존 제목/내용이 미리 채워진 form 페이지를 응답
    """
    # 1. 수정할 게시글 조회
    #    - 기존 값을 form의 value에 채워두기 위해 필요
    article = Article.objects.get(pk=article_pk)

    # 2. 템플릿에 넘겨줄 데이터를 딕셔너리로 묶기
    context = {
        'article': article,
    }

    # 3. 템플릿(edit.html)에 데이터를 채워 HTML을 만들고, 응답으로 반환
    return render(request, 'articles/edit.html', context)


def update(request, article_pk):
    """
    [게시글 수정 저장] - edit과 한 쌍 (POST)
    - edit 페이지의 form에서 제출된 데이터로 기존 게시글을 갱신
    - CRUD 중 UPDATE
    """
    # 1. 수정할 게시글 조회
    article = Article.objects.get(pk=article_pk)

    # 2. form에서 제출된 값으로 객체의 속성 덮어쓰기
    #    - 아직 DB에는 반영되지 않은 상태
    article.title = request.POST.get('title')
    article.content = request.POST.get('content')

    # 3. DB에 반영
    #    - 이미 pk가 있는 객체 => save()가 새로 만들지 않고 기존 데이터를 갱신
    article.save()

    # 4. 수정한 게시글의 상세 페이지로 redirect
    return redirect('articles:detail', article.pk)
