import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.shortcuts import redirect, render

from listings.selectors import marketplace_listings_for_user


def landing(request):
    visible_listings = marketplace_listings_for_user(request.user)
    featured_listings = list(visible_listings[:5])
    hero_listing = featured_listings[0] if featured_listings else None
    spotlight_listings = featured_listings[1:5] or featured_listings[:4]

    context = {
        "hero_listing": hero_listing,
        "spotlight_listings": spotlight_listings,
        "has_listing_only_access": request.user.is_authenticated and request.user.has_listing_only_access,
    }
    return render(request, "core/landing.html", context)


@login_required
def welcome(request):
    return redirect("users:dashboard")


def terms_of_service(request):
    return render(request, "core/terms_of_service.html")


def privacy_policy(request):
    return render(request, "core/privacy_policy.html")


def healthz(request):
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response


def readyz(request):
    checks = {}
    status_code = 200

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised in integration tests.
        checks["database"] = f"error:{type(exc).__name__}"
        status_code = 503

    try:
        cache_key = f"readyz:{uuid.uuid4().hex}"
        cache.set(cache_key, "ok", timeout=5)
        checks["cache"] = "ok" if cache.get(cache_key) == "ok" else "error:cache_miss"
        if checks["cache"] != "ok":
            status_code = 503
    except Exception as exc:  # pragma: no cover - exercised in integration tests.
        checks["cache"] = f"error:{type(exc).__name__}"
        status_code = 503

    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            raise RuntimeError("missing_channel_layer")
        async_to_sync(channel_layer.send)(f"readyz-{uuid.uuid4().hex}", {"type": "health.check"})
        checks["channel_layer"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised in integration tests.
        checks["channel_layer"] = f"error:{type(exc).__name__}"
        status_code = 503

    try:
        default_storage.exists("")
        checks["storage"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised in integration tests.
        checks["storage"] = f"error:{type(exc).__name__}"
        status_code = 503

    try:
        executor = MigrationExecutor(connections["default"])
        has_pending_migrations = bool(executor.migration_plan(executor.loader.graph.leaf_nodes()))
        checks["migrations"] = "ok" if not has_pending_migrations else "error:pending"
        if has_pending_migrations:
            status_code = 503
    except Exception as exc:  # pragma: no cover - exercised in integration tests.
        checks["migrations"] = f"error:{type(exc).__name__}"
        status_code = 503

    response = JsonResponse(
        {
            "status": "ok" if status_code == 200 else "error",
            "checks": checks,
        },
        status=status_code,
    )
    response["Cache-Control"] = "no-store"
    return response
