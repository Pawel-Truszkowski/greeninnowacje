from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def home(request):
    """Landing page; becomes the public tree map on M1 day 3."""
    return render(request, "core/home.html")
