from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

User = get_user_model()


def add_middleware(request):
    """Attach session and messages middleware for adapter tests."""
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    MessageMiddleware(lambda r: None).process_request(request)
    return request


def message_texts(request):
    return [message.message for message in get_messages(request)]
