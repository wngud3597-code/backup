from django import forms


class ArticleForm(forms.Form):
    # 사용자로부터 입력받을 필드와 입력값 검사 규칙을 정의
    title = forms.CharField(max_length=10)
    content = forms.CharField(widget=forms.Textarea)
