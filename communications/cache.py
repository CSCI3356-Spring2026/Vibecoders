from django.core.cache import cache


def global_unread_conversations_count_cache_key(user_id):
    return f"global-unread-conversations-count:{user_id}"


def clear_global_unread_conversations_count(user_id):
    if user_id:
        cache.delete(global_unread_conversations_count_cache_key(user_id))


def clear_global_unread_conversations_counts(*user_ids):
    for user_id in user_ids:
        clear_global_unread_conversations_count(user_id)
