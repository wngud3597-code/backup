from django.shortcuts import render


def introduce(request, username):
    context = {"username": username}
    return render(request, "my_app/introduce.html", context)
