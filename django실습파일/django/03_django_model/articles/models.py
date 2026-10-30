from django.db import models  # <== 기본적인 설계기능

# • 설계도(클래스): "블로그 글에는 제목(title)과 내용이 들어간다"라는 규칙.
# • 제품(인스턴스): "제목: 오늘 급식 레전드, 내용: 마라탕 나옴!" 공장에서 실제로 찍어내어 데이터베이스에 저장된 진짜 글 한 개.

# Create your models here.

# 게시글 저장을 위한 테이블을 설계
# 우리가 DB와 상호작용하는 것을 직접개발하려면 굉장히 많은것을 고려해야함
# 보관, 어떤 방식으로 소통을 할지, 여러기능 들(수정, 삭제...)
# 그래서 Django는 이러한 기본적인 설계 기능을 미리 구현을 해놓음 ==> model이라는 모듈에 구현
# 우리가 해야하는건 그냥 model모듈에서 필요한 클래스, 함수들을 잘가져다가 사용하는것
# 기본적인 model calss에 대한 구현이 완료된 Model클래스를 상속받으면서 시작


class Article(models.Model):  # <==상속받으면서 시작
    # 우리는 Model클래스를 상속받으면서 다른것들을 고민할필요없아
    # 지금해야할것 (테이블의 컬럼을 정의하고, 여러 재약조건들을 정의하는 일)에 대해서만 개발할수 있음
    # 컬럼을 정의할떄 'id'(primary key)는 django가 알아서 만들어주기 떄문에 생략이 가능하다
    # 칼럼은 클래스 변수로 정의(Collumn 정의)
    # 칼럼의 기본 틀(클래스) 자체도 django가 제공을 해줌
    # 인스탠스가 뭐지 하면 복습을 하고와야함 title에 적힌것 찰필드를 이해해야함

    title = models.CharField(
        max_length=100
    )  # <==제목은 글자수 제한이 필요함, 그래서 CharField를 사용, Constraints(제약조건): null=False, blank=False가 기본값으로 들어가있음
    content = (
        models.TextField()
    )  # <== 내용은 글자수 제한이 필요없음, 그래서 TextField를 사용


# 추가 필드 정의
create_at = models.DateTimeField(
    auto_now_add=True
)  # <== 글이 생성된 시간을 자동으로 기록, auto_now_add=True는 글이 생성될때만 기록됨
update_at = models.DateTimeField(
    auto_now=True
)  # <== 글이 수정된 시간을 자동으로 기록, auto_now=True는 글이 수정될때마다 기록됨
