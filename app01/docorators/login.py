from functools import wraps
from django.http import JsonResponse
from django.shortcuts import render
def is_login_func(func):
    @wraps(func)
    def inner(request, *args, **kwargs):
        if request.user.is_authenticated:
            return func(request, *args, **kwargs)
        return render(request, 'error/need_login.html')
    return inner


def is_login_method(method):
    @wraps(method)
    def inner(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return method(self, request, *args, **kwargs)
        return render(request, 'error/need_login.html')
    return inner
