from .services import role_of


def role(request):
    return {'role': role_of(request.user)}
