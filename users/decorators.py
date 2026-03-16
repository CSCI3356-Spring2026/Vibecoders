from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    """Decorator for function-based views: require login + Admin role, else 403."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_bc_admin:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return _wrapped


class AdminRequiredMixin(LoginRequiredMixin):
    """Mixin for class-based views: require login + Admin role, else 403."""

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        # super().dispatch may return a redirect for unauthenticated users
        if request.user.is_authenticated and not request.user.is_bc_admin:
            raise PermissionDenied
        return response
