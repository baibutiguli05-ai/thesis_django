from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .services import role_of


def role_required(role):
    """Тек көрсетілген рөлдегі пайдаланушыларды өткізеді, басқаларын өз кабинетіне жібереді."""
    def deco(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if role_of(request.user) != role:
                return redirect('home')
            return view(request, *args, **kwargs)
        return wrapper
    return deco
