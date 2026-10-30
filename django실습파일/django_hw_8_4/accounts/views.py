from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


def index(request):
    users = get_user_model().objects.all()
    return render(request, 'accounts/index.html', {'users': users})


def login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            auth_login(request, form.get_user())
            return redirect('accounts:index')
    else:
        form = AuthenticationForm(request)
    return render(request, 'accounts/login.html', {'form': form})


@require_POST
def logout(request):
    auth_logout(request)
    return redirect('accounts:index')
