from django.db import models

# Create your models here.

# [Model] 게시글(Article) 테이블의 '설계도'
# - DB와 직접 대화하려면 SQL 작성, 보안 처리, 생성/조회/수정/삭제 로직 등
#   신경 쓸 것이 매우 많음
# - Django는 이 기능들을 django.db.models 모듈에 미리 구현해 둠
#   => 우리는 SQL 대신 Python 클래스로 테이블을 설계하기만 하면 됨
# - models.Model 을 상속받는 순간, DB와 소통하는 모든 기본 기능을 물려받음

# 1. python manage.py makemigrations  -> 설계도를 '변경 이력 파일'로 기록
# 2. python manage.py migrate         -> 실제 DB에 테이블 생성 (테이블명: 앱이름_article)
class Article(models.Model):
    # Model을 상속받았으므로 우리가 할 일은 단 하나
    # => 어떤 컬럼이 필요한지, 각 컬럼에 어떤 제약조건이 있는지 정의하기

    # 컬럼 정의 규칙
    # - 클래스 변수 1개 = 테이블 컬럼 1개 (변수 이름이 곧 컬럼 이름)
    # - 오른쪽의 필드(Field) 클래스 = 컬럼의 데이터 타입 + 제약조건
    # - id 컬럼(자동 증가 PK)은 따로 적지 않아도 Django가 자동으로 생성

    title = models.CharField(max_length=10)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

