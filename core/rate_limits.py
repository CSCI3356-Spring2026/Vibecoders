import hashlib
import time

from django.core.cache import cache


def request_rate_limit_identifier(request):
    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    client_ip = forwarded_for or (request.META.get("REMOTE_ADDR") or "").strip() or "unknown"
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    user_agent_digest = hashlib.sha256(user_agent.encode("utf-8")).hexdigest()[:16]
    return f"{client_ip}:{user_agent_digest}"


def consume_rate_limit(*, scope, identifier, limit, window_seconds):
    if limit <= 0 or window_seconds <= 0:
        return True

    bucket = int(time.time() // window_seconds)
    cache_key = f"rate-limit:{scope}:{identifier}:{bucket}"
    if cache.add(cache_key, 1, timeout=window_seconds):
        return True

    try:
        current_count = cache.incr(cache_key)
    except ValueError:
        if cache.add(cache_key, 1, timeout=window_seconds):
            return True
        current_count = cache.incr(cache_key)

    return current_count <= limit
