from django.contrib import admin
# .models라고 작성하는 이유 : "명시적 상대 경로"
# Django의 표기 권장사항
from .models import Article

# Register your models here.

# admin site에 우리가 만든 Ariticle 모델 클래스를 등록.
admin.site.register(Article)
